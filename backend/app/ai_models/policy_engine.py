"""Rules-based governance policy compiler for the simulator."""

from __future__ import annotations

import re


class PolicyEngine:
    """Compile explicit policy rules into executable simulation rules.

    The governance module is intentionally rules-based. It does not infer
    meaning from free-form policy language. Instead, it accepts a small
    structured syntax such as:

    - resource_type=database; encryption=required; public_access=deny
    - resource_type=vm; max_cpu=70; max_memory=80; tag=Environment:Production
    """

    def parse_policy(self, policy_rule):
        rule_text = (policy_rule or '').strip()
        if not rule_text:
            return {'success': False, 'error': 'Policy rule is required'}

        compiled = self._compile_explicit_rule(rule_text)
        if not compiled['fields']:
            return {
                'success': False,
                'error': (
                    'Use explicit key=value rules such as '
                    '"resource_type=database; encryption=required; public_access=deny".'
                ),
            }

        return {
            'success': True,
            'confidence': 1.0,
            'parsed_rule': compiled,
        }

    def _compile_explicit_rule(self, rule_text):
        tokens = [token.strip() for token in re.split(r'[;\n,]+', rule_text) if token.strip()]
        fields = {}
        required_tags = []

        for token in tokens:
            if '=' not in token:
                continue
            key, value = [part.strip() for part in token.split('=', 1)]
            normalized_key = key.lower().replace(' ', '_')
            normalized_value = value.strip()

            if normalized_key in {'resource_type', 'type'}:
                fields['resource_type'] = normalized_value.lower()
            elif normalized_key in {'encryption', 'storage_encryption'}:
                fields['requires_encryption'] = normalized_value.lower() in {'required', 'true', 'yes', 'on'}
            elif normalized_key in {'public_access', 'public'}:
                fields['requires_public_block'] = normalized_value.lower() in {'deny', 'blocked', 'false', 'no', 'off'}
                fields['requires_private_access'] = fields['requires_public_block']
            elif normalized_key in {'tag', 'tags', 'required_tag'}:
                if ':' in normalized_value:
                    tag_key, tag_value = [part.strip() for part in normalized_value.split(':', 1)]
                    required_tags.append({'key': tag_key, 'value': tag_value})
                else:
                    required_tags.append({'key': normalized_value, 'value': normalized_value})
            elif normalized_key in {'max_cpu', 'cpu'}:
                fields['max_cpu'] = self._to_float(normalized_value)
            elif normalized_key in {'max_memory', 'memory'}:
                fields['max_memory'] = self._to_float(normalized_value)
            elif normalized_key in {'max_network', 'network'}:
                fields['max_network'] = self._to_float(normalized_value)
            elif normalized_key in {'severity'}:
                fields['severity'] = normalized_value.lower()
            elif normalized_key in {'policy_type', 'type_hint'}:
                fields['type'] = normalized_value.lower()

        if required_tags:
            fields['required_tags'] = required_tags

        fields.setdefault('type', 'custom')
        fields.setdefault('severity', 'medium')
        fields.setdefault('resource_type', None)
        fields.setdefault('requires_encryption', False)
        fields.setdefault('requires_private_access', False)
        fields.setdefault('requires_public_block', False)
        fields.setdefault('required_tags', [])
        fields.setdefault('max_cpu', None)
        fields.setdefault('max_memory', None)
        fields.setdefault('max_network', None)

        return {
            'expression': rule_text,
            'fields': fields,
        }

    def _to_float(self, value):
        try:
            return float(re.sub(r'[^0-9.\-]', '', value))
        except ValueError:
            return None

    def evaluate_resource(self, rule, resource):
        """Evaluate a compiled rule against a simulated resource."""
        violations = []
        resource_type = rule.get('resource_type')
        resource_kind = resource.get('resource_kind') or resource.get('type')
        if resource_type and resource_kind and resource_type != resource_kind:
            return {'compliant': True, 'violations': [], 'rule': rule, 'resource': resource}

        if rule.get('requires_encryption') and not resource.get('storage_encrypted', False):
            violations.append('Resource storage must be encrypted')

        if rule.get('requires_public_block') and resource.get('publicly_accessible', False):
            violations.append('Public access must be disabled')

        if rule.get('required_tags'):
            current_tags = {tag.get('key', '').lower(): tag.get('value', '') for tag in resource.get('tags', [])}
            current_tag_values = {value.lower() for value in current_tags.values()}
            for tag in rule['required_tags']:
                tag_key = (tag.get('key') or '').lower()
                tag_value = (tag.get('value') or '').lower()
                if tag_key in current_tags:
                    if tag_value and current_tags.get(tag_key, '').lower() != tag_value:
                        violations.append(f"Required tag value mismatch: {tag['key']}={tag['value']}")
                elif tag_value not in current_tag_values and tag_key not in current_tag_values:
                    violations.append(f"Required tag missing: {tag['key']}")

        cpu_limit = rule.get('max_cpu')
        if cpu_limit is not None and resource.get('cpu_utilization', 0) > cpu_limit:
            violations.append(f"CPU utilization exceeds {cpu_limit}%")

        memory_limit = rule.get('max_memory')
        if memory_limit is not None and resource.get('memory_utilization', 0) > memory_limit:
            violations.append(f"Memory utilization exceeds {memory_limit}%")

        network_limit = rule.get('max_network')
        if network_limit is not None:
            network_value = max(
                resource.get('network_in_mbps', 0) or 0,
                resource.get('network_out_mbps', 0) or 0,
            )
            if network_value > network_limit:
                violations.append(f"Network throughput exceeds {network_limit}")

        return {
            'compliant': len(violations) == 0,
            'violations': violations,
            'rule': rule,
            'resource': resource,
        }


policy_engine = PolicyEngine()
