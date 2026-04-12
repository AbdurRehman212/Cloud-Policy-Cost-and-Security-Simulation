from datetime import datetime
from flask import current_app
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, socketio
from app.models.resources import VirtualMachine, Database, ResourceTag, ResourceStatus
from app.models.organization import Organization, OrganizationMember
from app.models.governance import AuditLog
from app.config import Config
import random
import string
resource_bp = Blueprint('resources', __name__)
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
@resource_bp.route('/vm', methods=['POST'])
@jwt_required()
def create_vm():
    """Create virtual machine."""
    user_id = get_jwt_identity()
    data = request.get_json()
    org_id = data.get('organization_id')
    if not check_org_access(user_id, org_id, 'member'):
        return jsonify({'error': 'Access denied'}), 403
    # Check resource limits
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    current_resources = VirtualMachine.query.filter_by(organization_id=org_id).count()
    current_resources += Database.query.filter_by(organization_id=org_id).count()
    if current_resources >= org.max_resources:
        return jsonify({'error': 'Resource limit reached'}), 400
    # Pricing from config
    instance_type = data.get('instance_type', 't2.micro')
    hourly_rate = Config.VM_PRICING.get(instance_type, 0.0116)
    # Determine specs based on instance type
    specs = {
        't2.micro': {'vcpu': 1, 'memory_gb': 1.0, 'storage_gb': 8},
        't2.small': {'vcpu': 1, 'memory_gb': 2.0, 'storage_gb': 20},
        't2.medium': {'vcpu': 2, 'memory_gb': 4.0, 'storage_gb': 40},
        't2.large': {'vcpu': 2, 'memory_gb': 8.0, 'storage_gb': 80},
        'm5.large': {'vcpu': 2, 'memory_gb': 8.0, 'storage_gb': 100},
        'm5.xlarge': {'vcpu': 4, 'memory_gb': 16.0, 'storage_gb': 200}
    }.get(instance_type, {'vcpu': 1, 'memory_gb': 1.0, 'storage_gb': 8})
    vm = VirtualMachine(
        organization_id=org_id,
        name=data.get('name', 'unnamed-vm'),
        instance_id=generate_instance_id('i'),
        instance_type=instance_type,
        status=ResourceStatus.PENDING,
        vcpu=specs['vcpu'],
        memory_gb=specs['memory_gb'],
        storage_gb=data.get('storage_gb', specs['storage_gb']),
        cpu_utilization=random.uniform(8, 22),
        memory_utilization=random.uniform(12, 35),
        disk_read_iops=random.uniform(20, 80),
        disk_write_iops=random.uniform(10, 55),
        network_in_mbps=random.uniform(8, 35),
        network_out_mbps=random.uniform(6, 30),
        hourly_rate=hourly_rate,
        image_id=data.get('image_id', 'ami-12345678'),
        key_name=data.get('key_name'),
        private_ip=f"10.0.{random.randint(0,255)}.{random.randint(1,254)}"
    )
    db.session.add(vm)
    db.session.flush()
    # Add tags
    if data.get('tags'):
        for tag_key, tag_value in data['tags'].items():
            tag = ResourceTag(vm_id=vm.id, key=tag_key, value=tag_value)
            db.session.add(tag)
    # Audit log
    audit = AuditLog(
        organization_id=org_id,
        user_id=user_id,
        action='create',
        resource_type='vm',
        resource_id=vm.instance_id,
        new_values=vm.to_dict()
    )
    db.session.add(audit)
    db.session.commit()
    # Simulate provisioning delay
    from threading import Timer
    app = current_app._get_current_object()

    def provision_vm():
        with app.app_context():
            tracked_vm = VirtualMachine.query.filter_by(id=vm.id).first()
            if tracked_vm:
                tracked_vm.status = ResourceStatus.RUNNING
                tracked_vm.launched_at = datetime.utcnow()
                db.session.commit()
                socketio.emit('vm_status_change', {
                    'instance_id': tracked_vm.instance_id,
                    'status': 'running'
                }, room=f"org_{org_id}")
    Timer(3.0, provision_vm).start()
    return jsonify({
        'message': 'VM creation initiated',
        'vm': vm.to_dict()
    }), 201
@resource_bp.route('/vm', methods=['GET'])
@jwt_required()
def list_vms():
    """List virtual machines."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    if not check_org_access(user_id, org_id, 'viewer'):
        return jsonify({'error': 'Access denied'}), 403
    vms = VirtualMachine.query.filter_by(organization_id=org_id).all()
    return jsonify({'vms': [vm.to_dict() for vm in vms]}), 200
@resource_bp.route('/vm/<instance_id>', methods=['GET'])
@jwt_required()
def get_vm(instance_id):
    """Get VM details."""
    user_id = get_jwt_identity()
    vm = VirtualMachine.query.filter_by(instance_id=instance_id).first_or_404()
    if not check_org_access(user_id, vm.organization_id, 'viewer'):
        return jsonify({'error': 'Access denied'}), 403
    return jsonify(vm.to_dict()), 200
@resource_bp.route('/vm/<instance_id>/action', methods=['POST'])
@jwt_required()
def vm_action(instance_id):
    """Perform action on VM (start, stop, terminate)."""
    user_id = get_jwt_identity()
    data = request.get_json()
    action = data.get('action')
    vm = VirtualMachine.query.filter_by(instance_id=instance_id).first_or_404()
    if not check_org_access(user_id, vm.organization_id, 'member'):
        return jsonify({'error': 'Access denied'}), 403
    old_status = vm.status
    if action == 'stop':
        if vm.status == ResourceStatus.RUNNING:
            vm.status = ResourceStatus.STOPPED
            vm.stopped_at = datetime.utcnow()
            # Calculate runtime
            if vm.launched_at:
                runtime = (vm.stopped_at - vm.launched_at).total_seconds() / 3600
                vm.total_runtime_hours += runtime
    elif action == 'start':
        if vm.status == ResourceStatus.STOPPED:
            vm.status = ResourceStatus.RUNNING
            vm.launched_at = datetime.utcnow()
    elif action == 'terminate':
        vm.status = ResourceStatus.TERMINATED
        vm.terminated_at = datetime.utcnow()
        if vm.status == ResourceStatus.RUNNING and vm.launched_at:
            runtime = (vm.terminated_at - vm.launched_at).total_seconds() / 3600
            vm.total_runtime_hours += runtime
    else:
        return jsonify({'error': 'Invalid action'}), 400
    # Audit log
    audit = AuditLog(
        organization_id=vm.organization_id,
        user_id=user_id,
        action=action,
        resource_type='vm',
        resource_id=instance_id,
        old_values={'status': old_status.value if old_status else None},
        new_values={'status': vm.status.value if vm.status else None}
    )
    db.session.add(audit)
    db.session.commit()
    socketio.emit('vm_status_change', {
        'instance_id': vm.instance_id,
        'status': vm.status.value if vm.status else None
    }, room=f"org_{vm.organization_id}")
    return jsonify({
        'message': f'VM {action} successful',
        'vm': vm.to_dict()
    }), 200
@resource_bp.route('/db', methods=['POST'])
@jwt_required()
def create_database():
    """Create database instance."""
    user_id = get_jwt_identity()
    data = request.get_json()
    org_id = data.get('organization_id')
    if not check_org_access(user_id, org_id, 'member'):
        return jsonify({'error': 'Access denied'}), 403
    instance_class = data.get('instance_class', 'db.t2.micro')
    hourly_rate = Config.DB_PRICING.get(instance_class, 0.017)
    db_instance_id = generate_instance_id('db')
    db_instance = Database(
        organization_id=org_id,
        name=data.get('name', 'unnamed-db'),
        instance_id=db_instance_id,
        engine=data.get('engine', 'mysql'),
        engine_version=data.get('engine_version', '8.0'),
        instance_class=instance_class,
        status=ResourceStatus.PENDING,
        allocated_storage_gb=data.get('allocated_storage_gb', 20),
        free_storage_space=data.get('allocated_storage_gb', 20) * 0.72,
        cpu_utilization=random.uniform(5, 18),
        read_iops=random.uniform(90, 180),
        write_iops=random.uniform(40, 100),
        database_connections=random.randint(5, 25),
        master_username=data.get('master_username', 'admin'),
        publicly_accessible=data.get('publicly_accessible', False),
        storage_encrypted=data.get('storage_encrypted', False),
        hourly_rate=hourly_rate,
        endpoint=f"{db_instance_id.replace('db-', '')}.cluster-xyz.us-east-1.rds.amazonaws.com"
    )
    db.session.add(db_instance)
    db.session.commit()
    # Simulate provisioning
    from threading import Timer
    app = current_app._get_current_object()

    def provision_db():
        with app.app_context():
            tracked_db = Database.query.filter_by(id=db_instance.id).first()
            if tracked_db:
                tracked_db.status = ResourceStatus.RUNNING
                db.session.commit()
    Timer(5.0, provision_db).start()
    return jsonify({
        'message': 'Database creation initiated',
        'database': db_instance.to_dict()
    }), 201
@resource_bp.route('/db', methods=['GET'])
@jwt_required()
def list_databases():
    """List databases."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    if not check_org_access(user_id, org_id, 'viewer'):
        return jsonify({'error': 'Access denied'}), 403
    databases = Database.query.filter_by(organization_id=org_id).all()
    return jsonify({'databases': [db.to_dict() for db in databases]}), 200
@resource_bp.route('/metrics', methods=['GET'])
@jwt_required()
def get_resource_metrics():
    """Get aggregated resource metrics."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    if not check_org_access(user_id, org_id, 'viewer'):
        return jsonify({'error': 'Access denied'}), 403
    vms = VirtualMachine.query.filter_by(organization_id=org_id).all()
    databases = Database.query.filter_by(organization_id=org_id).all()
    total_vms = len(vms)
    running_vms = sum(1 for vm in vms if vm.status == ResourceStatus.RUNNING)
    total_dbs = len(databases)
    running_dbs = sum(1 for db in databases if db.status == ResourceStatus.RUNNING)
    # Calculate total hourly cost
    total_hourly_cost = sum(vm.hourly_rate for vm in vms if vm.status == ResourceStatus.RUNNING)
    total_hourly_cost += sum(db.hourly_rate for db in databases if db.status == ResourceStatus.RUNNING)
    # Average utilization
    avg_cpu = sum(vm.cpu_utilization for vm in vms if vm.status == ResourceStatus.RUNNING) / running_vms if running_vms > 0 else 0
    avg_memory = sum(vm.memory_utilization for vm in vms if vm.status == ResourceStatus.RUNNING) / running_vms if running_vms > 0 else 0
    avg_network = sum((vm.network_in_mbps + vm.network_out_mbps) for vm in vms if vm.status == ResourceStatus.RUNNING) / running_vms if running_vms > 0 else 0
    avg_db_cpu = sum(db.cpu_utilization for db in databases if db.status == ResourceStatus.RUNNING) / running_dbs if running_dbs > 0 else 0
    return jsonify({
        'summary': {
            'total_vms': total_vms,
            'running_vms': running_vms,
            'total_databases': total_dbs,
            'running_databases': running_dbs,
            'total_hourly_cost': round(total_hourly_cost, 4),
            'estimated_monthly_cost': round(total_hourly_cost * 730, 2),
            'average_cpu_utilization': round(avg_cpu, 2),
            'average_memory_utilization': round(avg_memory, 2),
            'average_network_throughput': round(avg_network, 2),
            'average_database_cpu': round(avg_db_cpu, 2),
        },
        'vms': [vm.to_dict() for vm in vms],
        'databases': [db.to_dict() for db in databases]
    }), 200
