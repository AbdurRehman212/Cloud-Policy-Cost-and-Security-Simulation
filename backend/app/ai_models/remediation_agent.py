"""Reinforcement-learning inspired remediation agent."""

from __future__ import annotations

from collections import defaultdict


class RemediationAgent:
    """A simple Q-learning inspired decision layer for remediation."""

    def __init__(self):
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.action_space = [
            'block_ip',
            'isolate_resource',
            'enable_encryption',
            'disable_public_access',
            'downsize_resource',
            'stop_idle_resource',
            'request_review',
            'scale_up',
        ]

    def _state_key(self, threat, resource):
        threat_type = (threat or {}).get('type') or (threat or {}).get('threat_type') or 'unknown'
        severity = (threat or {}).get('severity') or 'medium'
        resource_kind = (resource or {}).get('resource_kind') or (resource or {}).get('type') or 'unknown'
        public_access = 'public' if resource and resource.get('publicly_accessible') else 'private'
        idle = 'idle' if resource and resource.get('cpu_utilization', 100) < 10 else 'busy'
        return f'{threat_type}:{severity}:{resource_kind}:{public_access}:{idle}'

    def choose_actions(self, threat, resource):
        threat_type = (threat or {}).get('type') or (threat or {}).get('threat_type') or 'unknown'
        confidence = float((threat or {}).get('confidence', 0.5) or 0.5)
        resource_kind = (resource or {}).get('resource_kind') or (resource or {}).get('type') or 'unknown'
        state = self._state_key(threat, resource)

        actions = []
        if threat_type in {'ddos', 'brute_force', 'malware'}:
            actions.append('isolate_resource')
        if threat_type == 'ddos':
            actions.append('scale_up')
        if threat_type == 'brute_force':
            actions.append('block_ip')
        if resource_kind == 'database' and resource and resource.get('publicly_accessible'):
            actions.append('disable_public_access')
        if resource and not resource.get('storage_encrypted', True):
            actions.append('enable_encryption')
        if resource and resource.get('cpu_utilization', 100) < 10:
            actions.append('stop_idle_resource')
            actions.append('downsize_resource')
        if confidence < 0.75:
            actions.append('request_review')

        if not actions:
            actions.append('request_review')

        ranked = []
        for action in actions:
            ranked.append((self.q_table[state][action], action))
        ranked.sort(reverse=True)
        ordered = [action for _, action in ranked]
        if not ordered:
            ordered = actions
        return ordered

    def remediate(self, threat, resource):
        """Return structured remediation steps for the UI and routes."""
        actions = self.choose_actions(threat, resource)
        results = []
        requires_approval = False

        for action in actions:
            if action in {'downsize_resource', 'stop_idle_resource', 'disable_public_access', 'enable_encryption'}:
                requires_approval = True
            results.append({
                'action': action,
                'status': 'success',
                'details': self._build_details(action, threat, resource),
            })

        return {
            'requires_approval': requires_approval,
            'results': results,
            'recommendation': actions[0] if actions else 'request_review',
        }

    def _build_details(self, action, threat, resource):
        if action == 'block_ip':
            return 'Block the suspicious source IP range and add a temporary firewall rule.'
        if action == 'isolate_resource':
            return 'Move the resource to an isolated security group and pause sensitive traffic.'
        if action == 'enable_encryption':
            return 'Enable storage encryption for the affected resource.'
        if action == 'disable_public_access':
            return 'Disable public access and restrict access to the private network.'
        if action == 'downsize_resource':
            return 'Downsize the instance to reduce waste and operating cost.'
        if action == 'stop_idle_resource':
            return 'Stop the idle resource until it is needed again.'
        if action == 'scale_up':
            return 'Scale the workload capacity to absorb the traffic spike.'
        return 'Escalate for human review.'

    def learn(self, state, action, reward):
        """Lightweight Q-value update for future action ranking."""
        current = self.q_table[state][action]
        self.q_table[state][action] = current + 0.2 * (reward - current)


remediation_agent = RemediationAgent()
