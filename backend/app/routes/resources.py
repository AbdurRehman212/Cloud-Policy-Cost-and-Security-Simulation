from datetime import datetime
from flask import current_app
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, socketio
from app.services.resource_simulator import resource_simulator
from app.services.simulation_engine import generate_metrics
from app.models.resources import VirtualMachine, Database, ResourceTag, ResourceStatus
from app.models.organization import Organization, OrganizationMember, ensure_default_organization_membership
from app.models.user import User
from app.models.governance import AuditLog
from app.config import Config
from threading import Lock
from time import monotonic
import logging
import math
import random
import string
resource_bp = Blueprint('resources', __name__)
logger = logging.getLogger(__name__)

# In-memory simulator resource state for Module 3 demo flows.
RESOURCES = []
_RESOURCE_ID_SEQ = 1
_RESOURCE_LOCK = Lock()
_RESOURCE_UPDATER_LOCK = Lock()
_RESOURCE_UPDATER_RUNNING = False
_RESOURCE_UPDATER_TASK = None
_RESOURCE_LAST_UPDATE_MONOTONIC = 0.0
RESOURCE_UPDATE_INTERVAL_SECONDS = 5


def _success(data, status_code=200):
    return jsonify({'status': 'success', 'data': data}), status_code


def _error(message, status_code=400, code='bad_request'):
    return jsonify({'status': 'error', 'error': {'message': message}}), status_code


def _next_resource_id():
    """Return a unique in-memory resource id."""
    global _RESOURCE_ID_SEQ
    next_id = _RESOURCE_ID_SEQ
    _RESOURCE_ID_SEQ += 1
    return next_id


def _ensure_org_membership(user_id):
    memberships = (
        OrganizationMember.query
        .filter_by(user_id=user_id)
        .order_by(OrganizationMember.joined_at.asc(), OrganizationMember.id.asc())
        .all()
    )
    if memberships:
        return {membership.organization_id for membership in memberships}

    user = User.query.get(user_id)
    if not user:
        return set()

    organization, _, created = ensure_default_organization_membership(user)
    if created:
        db.session.commit()
    return {organization.id}


def _resolve_org_id_for_user(user_id, preferred_org_id=None):
    allowed_org_ids = _ensure_org_membership(user_id)
    if not allowed_org_ids:
        return None

    if preferred_org_id is not None:
        try:
            preferred_org_id = int(preferred_org_id)
        except (TypeError, ValueError):
            preferred_org_id = None
    if preferred_org_id in allowed_org_ids:
        return preferred_org_id
    return sorted(allowed_org_ids)[0]


def _sanitize_metric(value, fallback=0.05):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = fallback
    return round(max(0.0, min(1.0, value)), 4)


def _resource_envelope(resource):
    if not isinstance(resource, dict):
        return None
    if not resource.get('id'):
        return None

    name = (resource.get('name') or '').strip()
    if not name:
        name = f"resource-{resource['id']}"

    status = (resource.get('status') or 'stopped').strip().lower()
    if status not in {'creating', 'running', 'stopped', 'terminated'}:
        status = 'stopped'

    now_iso = datetime.utcnow().isoformat()
    seed = resource.get('seed')
    if seed is None:
        return None
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        return None

    envelope = {
        'id': resource['id'],
        'name': name,
        'type': resource.get('type') or 'vm',
        'engine': resource.get('engine'),
        'cpu': _sanitize_metric(resource.get('cpu'), fallback=0.02),
        'memory': _sanitize_metric(resource.get('memory'), fallback=0.03),
        'status': status,
        'base_cpu': _sanitize_metric(resource.get('base_cpu', resource.get('cpu')), fallback=0.02),
        'base_memory': _sanitize_metric(resource.get('base_memory', resource.get('memory')), fallback=0.03),
        'seed': seed,
        'org_id': resource.get('org_id'),
        'created_at': resource.get('created_at') or now_iso,
        'last_updated': resource.get('last_updated') or now_iso,
    }

    # Guard response payloads used by the frontend.
    for required in (
        'id',
        'name',
        'type',
        'org_id',
        'status',
        'cpu',
        'memory',
        'base_cpu',
        'base_memory',
        'seed',
        'last_updated',
    ):
        if envelope.get(required) is None:
            return None

    if envelope['type'] not in {'vm', 'database'}:
        return None

    return envelope


def _seeded_variation(seed, step, min_pct=0.05, max_pct=0.10):
    """Deterministic bounded variation by resource seed and update step."""
    prng = random.Random((int(seed) * 1315423911) + int(step))
    magnitude = prng.uniform(min_pct, max_pct)
    return magnitude if prng.random() >= 0.5 else -magnitude


def _evolve_metric(previous, target, seed, step):
    variation = _seeded_variation(seed, step)
    blended = (float(previous) * 0.78) + (float(target) * 0.22)
    adjusted = blended * (1.0 + variation)
    return _sanitize_metric(adjusted, fallback=target)


def _task_is_alive(task):
    if task is None:
        return False

    alive_callable = getattr(task, 'is_alive', None)
    if callable(alive_callable):
        try:
            return bool(alive_callable())
        except Exception:
            return True

    dead_flag = getattr(task, 'dead', None)
    if dead_flag is not None:
        return not bool(dead_flag)

    return True


def _update_resources_with_simulation(force=False):
    """Refresh in-memory resource CPU/memory from simulation engine snapshots."""
    global _RESOURCE_LAST_UPDATE_MONOTONIC

    with _RESOURCE_LOCK:
        now_mono = monotonic()
        if not force and (now_mono - _RESOURCE_LAST_UPDATE_MONOTONIC) < RESOURCE_UPDATE_INTERVAL_SECONDS:
            return False

        running_resources = [resource for resource in RESOURCES if resource.get('status') == 'running' and resource.get('id')]
        metrics = generate_metrics(points=1) if running_resources else []
        base_metric = metrics[0] if metrics else {}
        dataset_cpu = _sanitize_metric(base_metric.get('cpu'), fallback=0.4)
        dataset_memory = _sanitize_metric(base_metric.get('memory'), fallback=0.35)
        now_iso = datetime.utcnow().isoformat()

        for resource in running_resources:
            seed = int(resource.get('seed') or random.randint(1000, 999999))
            resource['seed'] = seed
            step = int(resource.get('_step', 0)) + 1
            resource['_step'] = step

            # Stable resource identity offset so each resource follows its own curve.
            phase = ((seed % 360) + step) % 360
            cpu_offset = 0.08 * math.sin(math.radians(phase))
            mem_offset = 0.07 * math.cos(math.radians((phase * 3) % 360))

            resource_base_cpu = _sanitize_metric(resource.get('base_cpu'), fallback=dataset_cpu)
            resource_base_memory = _sanitize_metric(resource.get('base_memory'), fallback=dataset_memory)
            target_cpu = _sanitize_metric(
                resource_base_cpu + cpu_offset + ((dataset_cpu - resource_base_cpu) * 0.08),
                fallback=resource_base_cpu,
            )
            target_memory = _sanitize_metric(
                resource_base_memory + mem_offset + ((dataset_memory - resource_base_memory) * 0.08),
                fallback=resource_base_memory,
            )

            resource['cpu'] = _evolve_metric(resource.get('cpu', target_cpu), target_cpu, seed, step)
            resource['memory'] = _evolve_metric(resource.get('memory', target_memory), target_memory, seed + 17, step)
            resource['last_updated'] = base_metric.get('time') or now_iso

        for resource in RESOURCES:
            if not resource.get('id'):
                continue
            if resource.get('status') == 'running':
                continue
            resource['cpu'] = _sanitize_metric(resource.get('cpu', 0.02), fallback=0.02)
            resource['memory'] = _sanitize_metric(resource.get('memory', 0.03), fallback=0.03)
            resource['last_updated'] = now_iso

        _RESOURCE_LAST_UPDATE_MONOTONIC = now_mono
    return True


def _resource_update_loop():
    """Background updater for in-memory resource metrics."""
    while True:
        try:
            _update_resources_with_simulation(force=True)
            with _RESOURCE_LOCK:
                snapshot = [
                    payload for payload in (_resource_envelope(dict(resource)) for resource in RESOURCES)
                    if payload is not None
                ]
            socketio.emit('resources:update', {
                'status': 'success',
                'data': snapshot,
            })
        except Exception:
            # Keep loop resilient for demo runtime.
            logger.exception('Failed to refresh in-memory resource simulation state')
        socketio.sleep(RESOURCE_UPDATE_INTERVAL_SECONDS)


def _complete_resource_creation(resource_id):
    # Transition from creating to running after a short provisioning window.
    socketio.sleep(random.uniform(2.0, 3.0))
    with _RESOURCE_LOCK:
        for resource in RESOURCES:
            if resource.get('id') != resource_id:
                continue
            if resource.get('status') == 'creating':
                resource['status'] = 'running'
                resource['last_updated'] = datetime.utcnow().isoformat()
            break


def start_resource_updates():
    """Start the shared resource updater only once."""
    global _RESOURCE_UPDATER_RUNNING, _RESOURCE_UPDATER_TASK

    with _RESOURCE_UPDATER_LOCK:
        if _RESOURCE_UPDATER_RUNNING and _task_is_alive(_RESOURCE_UPDATER_TASK):
            return
        if _task_is_alive(_RESOURCE_UPDATER_TASK):
            _RESOURCE_UPDATER_RUNNING = True
            return
        _RESOURCE_UPDATER_RUNNING = True
        _RESOURCE_UPDATER_TASK = socketio.start_background_task(_resource_update_loop)


def generate_instance_id(prefix='i'):
    """Generate unique instance ID."""
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=17))
    return f"{prefix}-{suffix}"
def check_org_access(user_id, org_id, min_role='member'):
    """Check if user has access to organization."""
    member = OrganizationMember.query.filter_by(
        organization_id=org_id,
        user_id=user_id
    ).first()
    if not member:
        return None
    role_hierarchy = {'viewer': 1, 'member': 2, 'admin': 3, 'owner': 4}
    if role_hierarchy.get(member.role, 0) < role_hierarchy.get(min_role, 2):
        return None
    return member


@resource_bp.route('', methods=['GET'])
@jwt_required()
def list_resources():
    """Return in-memory simulated resources for the user's organizations."""
    user_id = get_jwt_identity()
    org_id_filter = request.args.get('organization_id', type=int)
    current_org_id = _resolve_org_id_for_user(user_id)
    if current_org_id is None:
        return _success([])
    if org_id_filter is not None and org_id_filter != current_org_id:
        return _error('Access denied for organization.', status_code=403, code='forbidden')

    _update_resources_with_simulation(force=False)

    scoped_resources = []
    with _RESOURCE_LOCK:
        for resource in RESOURCES:
            if resource.get('org_id') != current_org_id:
                continue
            payload = _resource_envelope(dict(resource))
            if payload is None:
                continue
            scoped_resources.append(payload)

    return _success(scoped_resources)


def _create_in_memory_resource(user_id, data, resource_type):
    org_id = _resolve_org_id_for_user(
        user_id,
        data.get('org_id', data.get('organization_id')),
    )
    if org_id is None:
        return None, _error('No organization available for this user.', status_code=404, code='organization_missing')

    name_prefix = 'DB' if resource_type == 'database' else 'VM'
    now_iso = datetime.utcnow().isoformat()
    dataset_points = generate_metrics(points=1)
    dataset_base = dataset_points[0] if dataset_points else {}
    base_cpu = _sanitize_metric(dataset_base.get('cpu'), fallback=0.05)
    base_memory = _sanitize_metric(dataset_base.get('memory'), fallback=0.07)

    with _RESOURCE_LOCK:
        resource_id = _next_resource_id()
        name = (data.get('name') or f'{name_prefix}-{resource_id}').strip() or f'{name_prefix}-{resource_id}'

        resource = {
            'id': resource_id,
            'name': name,
            'type': resource_type,
            'engine': data.get('engine', 'PostgreSQL') if resource_type == 'database' else None,
            'cpu': base_cpu,
            'memory': base_memory,
            'base_cpu': base_cpu,
            'base_memory': base_memory,
            'status': 'creating',
            'seed': random.randint(1000, 999999),
            '_step': 0,
            'org_id': org_id,
            'created_at': now_iso,
            'last_updated': now_iso,
        }
        RESOURCES.append(resource)

    _update_resources_with_simulation(force=True)
    socketio.start_background_task(_complete_resource_creation, resource_id)

    with _RESOURCE_LOCK:
        created = next((item for item in RESOURCES if item.get('id') == resource_id), resource)
        payload = _resource_envelope(dict(created))

    if payload is None:
        return None, _error('Resource provisioning failed.', status_code=500, code='resource_invalid')
    return payload, None


@resource_bp.route('/create', methods=['POST'])
@jwt_required()
def create_resource():
    """Create a simulated VM or database in memory."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    resource_type = (request.args.get('type') or data.get('type') or 'vm').strip().lower()
    if resource_type in {'db', 'database'}:
        resource_type = 'database'
    else:
        resource_type = 'vm'

    payload, error_response = _create_in_memory_resource(user_id, data, resource_type)
    if error_response is not None:
        return error_response
    return _success(payload, status_code=201)


@resource_bp.route('/<int:resource_id>', methods=['DELETE'])
@jwt_required()
def delete_resource(resource_id):
    """Delete a simulated resource safely from memory."""
    user_id = get_jwt_identity()
    allowed_org_ids = _ensure_org_membership(user_id)

    with _RESOURCE_LOCK:
        for index, resource in enumerate(RESOURCES):
            if resource.get('id') != resource_id:
                continue
            if resource.get('org_id') not in allowed_org_ids:
                return _error('Access denied for resource.', status_code=403, code='forbidden')

            removed = RESOURCES.pop(index)
            payload = _resource_envelope(dict(removed))
            if payload is None:
                return _error('Resource state is invalid.', status_code=500, code='resource_invalid')
            return _success(payload)

    return _error('Resource not found.', status_code=404, code='not_found')


@resource_bp.route('/<int:resource_id>/stop', methods=['POST'])
@jwt_required()
def stop_resource(resource_id):
    """Stop a simulated resource and reduce utilization."""
    user_id = get_jwt_identity()
    allowed_org_ids = _ensure_org_membership(user_id)

    with _RESOURCE_LOCK:
        for resource in RESOURCES:
            if resource.get('id') != resource_id:
                continue
            if resource.get('org_id') not in allowed_org_ids:
                return _error('Access denied for resource.', status_code=403, code='forbidden')

            resource['status'] = 'stopped'
            resource['cpu'] = _sanitize_metric(float(resource.get('cpu', 0.05)) * 0.2, fallback=0.02)
            resource['memory'] = _sanitize_metric(float(resource.get('memory', 0.05)) * 0.3, fallback=0.03)
            resource['last_updated'] = datetime.utcnow().isoformat()
            payload = _resource_envelope(dict(resource))
            if payload is None:
                return _error('Resource state is invalid.', status_code=500, code='resource_invalid')
            return _success(payload)

    return _error('Resource not found.', status_code=404, code='not_found')


@resource_bp.route('/vm', methods=['POST'])
@jwt_required()
def create_vm():
    """Create virtual machine."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    org_id = data.get('organization_id')
    if not check_org_access(user_id, org_id, 'member'):
        return _error('Access denied', status_code=403, code='forbidden')
    payload, error_response = _create_in_memory_resource(user_id, data, 'vm')
    if error_response is not None:
        return error_response
    return _success({
        'message': 'VM creation initiated',
        'vm': payload
    }, status_code=201)
@resource_bp.route('/vm', methods=['GET'])
@jwt_required()
def list_vms():
    """List virtual machines."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    if not check_org_access(user_id, org_id, 'viewer'):
        return _error('Access denied', status_code=403, code='forbidden')
    _update_resources_with_simulation(force=False)
    with _RESOURCE_LOCK:
        vms = [
            payload
            for payload in (_resource_envelope(dict(resource)) for resource in RESOURCES)
            if payload is not None and payload.get('org_id') == org_id and payload.get('type') == 'vm'
        ]
    return _success({'vms': vms})
@resource_bp.route('/vm/<instance_id>', methods=['GET'])
@jwt_required()
def get_vm(instance_id):
    """Get VM details."""
    user_id = get_jwt_identity()
    vm_id = None
    try:
        vm_id = int(instance_id)
    except (TypeError, ValueError):
        vm_id = None
    if vm_id is None:
        return _error('VM not found', status_code=404, code='not_found')

    allowed_org_ids = _ensure_org_membership(user_id)
    with _RESOURCE_LOCK:
        for resource in RESOURCES:
            if resource.get('id') != vm_id or resource.get('type') != 'vm':
                continue
            if resource.get('org_id') not in allowed_org_ids:
                return _error('Access denied', status_code=403, code='forbidden')
            payload = _resource_envelope(dict(resource))
            if payload is None:
                return _error('VM state is invalid.', status_code=500, code='resource_invalid')
            return _success(payload)
    return _error('VM not found', status_code=404, code='not_found')
@resource_bp.route('/vm/<instance_id>/action', methods=['POST'])
@jwt_required()
def vm_action(instance_id):
    """Perform action on VM (start, stop, terminate)."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    action = data.get('action')
    try:
        vm_id = int(instance_id)
    except (TypeError, ValueError):
        vm_id = None
    if vm_id is None:
        return _error('VM not found', status_code=404, code='not_found')

    allowed_org_ids = _ensure_org_membership(user_id)
    with _RESOURCE_LOCK:
        target = None
        for resource in RESOURCES:
            if resource.get('id') == vm_id and resource.get('type') == 'vm':
                target = resource
                break
        if not target:
            return _error('VM not found', status_code=404, code='not_found')
        if target.get('org_id') not in allowed_org_ids:
            return _error('Access denied', status_code=403, code='forbidden')

        if action == 'stop':
            target['status'] = 'stopped'
            target['cpu'] = _sanitize_metric(float(target.get('cpu', 0.05)) * 0.2, fallback=0.02)
            target['memory'] = _sanitize_metric(float(target.get('memory', 0.05)) * 0.3, fallback=0.03)
        elif action == 'start':
            if target.get('status') == 'stopped':
                target['status'] = 'running'
        elif action == 'terminate':
            target['status'] = 'terminated'
        else:
            return _error('Invalid action', status_code=400, code='bad_request')

        target['last_updated'] = datetime.utcnow().isoformat()
        payload = _resource_envelope(dict(target))
        if payload is None:
            return _error('VM state is invalid.', status_code=500, code='resource_invalid')

    return _success({
        'message': f'VM {action} successful',
        'vm': payload
    })
@resource_bp.route('/db/<instance_id>/action', methods=['POST'])
@jwt_required()
def database_action(instance_id):
    """Perform an action on a database instance (start, stop, terminate)."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    action = data.get('action')
    try:
        database_id = int(instance_id)
    except (TypeError, ValueError):
        database_id = None
    if database_id is None:
        return _error('Database not found', status_code=404, code='not_found')

    allowed_org_ids = _ensure_org_membership(user_id)
    with _RESOURCE_LOCK:
        target = None
        for resource in RESOURCES:
            if resource.get('id') == database_id and resource.get('type') == 'database':
                target = resource
                break
        if not target:
            return _error('Database not found', status_code=404, code='not_found')
        if target.get('org_id') not in allowed_org_ids:
            return _error('Access denied', status_code=403, code='forbidden')

        if action == 'stop':
            target['status'] = 'stopped'
            target['cpu'] = _sanitize_metric(float(target.get('cpu', 0.05)) * 0.2, fallback=0.02)
            target['memory'] = _sanitize_metric(float(target.get('memory', 0.05)) * 0.3, fallback=0.03)
        elif action == 'start':
            if target.get('status') == 'stopped':
                target['status'] = 'running'
        elif action == 'terminate':
            target['status'] = 'terminated'
        else:
            return _error('Invalid action', status_code=400, code='bad_request')

        target['last_updated'] = datetime.utcnow().isoformat()
        payload = _resource_envelope(dict(target))
        if payload is None:
            return _error('Database state is invalid.', status_code=500, code='resource_invalid')

    return _success({
        'message': f'Database {action} successful',
        'database': payload
    })
@resource_bp.route('/db', methods=['POST'])
@jwt_required()
def create_database():
    """Create database instance."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    org_id = data.get('organization_id')
    if not check_org_access(user_id, org_id, 'member'):
        return _error('Access denied', status_code=403, code='forbidden')
    payload, error_response = _create_in_memory_resource(user_id, data, 'database')
    if error_response is not None:
        return error_response
    return _success({
        'message': 'Database creation initiated',
        'database': payload
    }, status_code=201)
@resource_bp.route('/db', methods=['GET'])
@jwt_required()
def list_databases():
    """List databases."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    if not check_org_access(user_id, org_id, 'viewer'):
        return _error('Access denied', status_code=403, code='forbidden')
    _update_resources_with_simulation(force=False)
    with _RESOURCE_LOCK:
        databases = [
            payload
            for payload in (_resource_envelope(dict(resource)) for resource in RESOURCES)
            if payload is not None and payload.get('org_id') == org_id and payload.get('type') == 'database'
        ]
    return _success({'databases': databases})
@resource_bp.route('/metrics', methods=['GET'])
@jwt_required()
def get_resource_metrics():
    """Get aggregated resource metrics."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    if not check_org_access(user_id, org_id, 'viewer'):
        return _error('Access denied', status_code=403, code='forbidden')
    _update_resources_with_simulation(force=False)
    with _RESOURCE_LOCK:
        scoped_resources = [
            payload
            for payload in (_resource_envelope(dict(resource)) for resource in RESOURCES)
            if payload is not None and payload.get('org_id') == org_id
        ]

    vms = [resource for resource in scoped_resources if resource.get('type') == 'vm']
    databases = [resource for resource in scoped_resources if resource.get('type') == 'database']
    running_resources = [resource for resource in scoped_resources if resource.get('status') == 'running']

    total_vms = len(vms)
    running_vms = sum(1 for vm in vms if vm.get('status') == 'running')
    total_dbs = len(databases)
    running_dbs = sum(1 for db in databases if db.get('status') == 'running')
    avg_cpu = (
        sum(float(resource.get('cpu', 0.0)) for resource in running_resources) / len(running_resources)
        if running_resources else 0.0
    )
    avg_memory = (
        sum(float(resource.get('memory', 0.0)) for resource in running_resources) / len(running_resources)
        if running_resources else 0.0
    )

    return _success({
        'summary': {
            'total_vms': total_vms,
            'running_vms': running_vms,
            'total_databases': total_dbs,
            'running_databases': running_dbs,
            'total_hourly_cost': 0.0,
            'estimated_monthly_cost': 0.0,
            'average_cpu_utilization': round(avg_cpu, 2),
            'average_memory_utilization': round(avg_memory, 2),
            'average_network_throughput': 0.0,
            'average_database_cpu': round(
                sum(float(resource.get('cpu', 0.0)) for resource in databases if resource.get('status') == 'running') / running_dbs,
                2,
            ) if running_dbs > 0 else 0.0,
        },
        'cost_trend': [],
        'utilization_trend': [],
        'recent_activity': [],
        'vms': vms,
        'databases': databases
    })
