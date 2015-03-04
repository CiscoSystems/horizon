# Copyright 2013, Big Switch Networks, Inc
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging

from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import messages
from horizon.utils import validators

from openstack_dashboard import api
from openstack_dashboard.dashboards.project.firewalls import utils

port_validator = validators.validate_port_or_colon_separated_port_range

LOG = logging.getLogger(__name__)


class UpdateRule(forms.SelfHandlingForm):
    name = forms.CharField(max_length=80, label=_("Name"), required=False)
    description = forms.CharField(
        required=False,
        max_length=80, label=_("Description"))
    protocol = forms.ChoiceField(
        label=_("Protocol"), required=False,
        choices=[('TCP', _('TCP')), ('UDP', _('UDP')), ('ICMP', _('ICMP')),
                 ('ANY', _('ANY'))],
        help_text=_('Protocol for the firewall rule'))
    action = forms.ChoiceField(
        label=_("Action"), required=False,
        choices=[('ALLOW', _('ALLOW')), ('DENY', _('DENY'))],
        help_text=_('Action for the firewall rule'))
    source_ip_address = forms.IPField(
        label=_("Source IP Address/Subnet"),
        version=forms.IPv4 | forms.IPv6,
        required=False, mask=True,
        help_text=_('Source IP address or subnet'))
    destination_ip_address = forms.IPField(
        label=_('Destination IP Address/Subnet'),
        version=forms.IPv4 | forms.IPv6,
        required=False, mask=True,
        help_text=_('Destination IP address or subnet'))
    source_port = forms.CharField(
        max_length=80,
        label=_("Source Port/Port Range"),
        required=False,
        validators=[port_validator],
        help_text=_('Source port (integer in [1, 65535] or range in a:b)'))
    destination_port = forms.CharField(
        max_length=80,
        label=_("Destination Port/Port Range"),
        required=False,
        validators=[port_validator],
        help_text=_('Destination port (integer in [1, 65535] or range'
                    ' in a:b)'))
    shared = forms.BooleanField(label=_("Shared"), required=False)
    enabled = forms.BooleanField(label=_("Enabled"), required=False)

    failure_url = 'horizon:project:firewalls:index'

    def handle(self, request, context):
        rule_id = self.initial['rule_id']
        name_or_id = context.get('name') or rule_id
        if context['protocol'] == 'ANY':
            context['protocol'] = None
        for f in ['source_ip_address', 'destination_ip_address',
                  'source_port', 'destination_port']:
            if not context[f]:
                context[f] = None
        try:
            rule = api.fwaas.rule_update(request, rule_id, **context)
            msg = _('Rule %s was successfully updated.') % name_or_id
            LOG.debug(msg)
            messages.success(request, msg)
            return rule
        except Exception as e:
            msg = (_('Failed to update rule %(name)s: %(reason)s') %
                   {'name': name_or_id, 'reason': e})
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)


class UpdatePolicy(forms.SelfHandlingForm):
    name = forms.CharField(max_length=80, label=_("Name"), required=False)
    description = forms.CharField(required=False,
                                  max_length=80, label=_("Description"))
    shared = forms.BooleanField(label=_("Shared"), required=False)
    audited = forms.BooleanField(label=_("Audited"), required=False)

    failure_url = 'horizon:project:firewalls:index'

    def handle(self, request, context):
        policy_id = self.initial['policy_id']
        name_or_id = context.get('name') or policy_id
        try:
            policy = api.fwaas.policy_update(request, policy_id, **context)
            msg = _('Policy %s was successfully updated.') % name_or_id
            LOG.debug(msg)
            messages.success(request, msg)
            return policy
        except Exception as e:
            msg = _('Failed to update policy %(name)s: %(reason)s') % {
                'name': name_or_id, 'reason': e}
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)


class UpdateFirewall(forms.SelfHandlingForm):
    name = forms.CharField(max_length=80,
                           label=_("Name"),
                           required=False)
    description = forms.CharField(max_length=80,
                                  label=_("Description"),
                                  required=False)
    firewall_policy_id = forms.ChoiceField(label=_("Policy"))
    admin_state_up = forms.ChoiceField(choices=[(True, _('UP')),
                                                (False, _('DOWN'))],
                                       label=_("Admin State"))
    port_id, direction = utils.set_port_id_and_direction()

    failure_url = 'horizon:project:firewalls:index'

    def __init__(self, request, *args, **kwargs):
        super(UpdateFirewall, self).__init__(request, *args, **kwargs)

        try:
            tenant_id = self.request.user.tenant_id
            policies = api.fwaas.policy_list_for_tenant(request, tenant_id)
            policies = sorted(policies, key=lambda policy: policy.name)
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve policy list.'))
            policies = []

        policy_id = kwargs['initial']['firewall_policy_id']
        policy_name = [p.name for p in policies if p.id == policy_id][0]

        firewall_policy_id_choices = [(policy_id, policy_name)]
        for p in policies:
            if p.id != policy_id:
                firewall_policy_id_choices.append((p.id, p.name_or_id))

        self.fields['firewall_policy_id'].choices = firewall_policy_id_choices

        if api.fwaas.get_firewall_provider():
            self.fields['port_id'].choices = self._port_id_choices(
                request, tenant_id, kwargs['initial']['port_id'])
            self.fields['direction'].choices = self._direction_choices(
                kwargs['initial']['direction'])

    def _port_id_choices(self, request, tenant_id, port_id):
        port_id_choices = [('', _("Select an Interface"))]
        try:
            port = api.neutron.port_get(request, port_id)
        except Exception:
            exceptions.handle(request, _('Unable to retrieve port.'))
        try:
            router = api.neutron.router_get(request, port.device_id)
        except Exception:
            exceptions.handle(request, _('Unable to retrieve router.'))

        p_ip = router.name + ' / ' + port.fixed_ips[0]['ip_address']
        port_id_choices = [(port_id, p_ip)]
        try:
            ports = api.neutron.port_list(request, tenant_id=tenant_id)
        except Exception:
            exceptions.handle(request, _('Unable to retrieve port list.'))
        for p in ports:
            if p.id != port_id:
                if p.device_id == port.device_id:
                    p_ip = router.name + ' / ' + p.fixed_ips[0]['ip_address']
                    port_id_choices.append((p.id, p_ip))

        return port_id_choices

    def _direction_choices(self, direction):
        direction_choices = [('both', _('BOTH')),
                             ('outside', _('OUTSIDE')),
                             ('inside', _('INSIDE'))]
        for d in direction_choices:
            if d[0] == direction.lower():
                direction_choices.remove(d)
                break
        direction_choices.insert(0, d)
        return direction_choices

    def handle(self, request, context):
        firewall_id = self.initial['firewall_id']
        name_or_id = context.get('name') or firewall_id
        context['admin_state_up'] = (context['admin_state_up'] == 'True')
        try:
            if not api.fwaas.get_firewall_provider():
                if 'port_id' in context:
                    context.pop('port_id')
                if 'direction' in context:
                    context.pop('direction')
            firewall = api.fwaas.firewall_update(request, firewall_id,
                                                 **context)
            msg = _('Firewall %s was successfully updated.') % name_or_id
            LOG.debug(msg)
            messages.success(request, msg)
            return firewall
        except Exception as e:
            msg = _('Failed to update firewall %(name)s: %(reason)s') % {
                'name': name_or_id, 'reason': e}
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)


class InsertRuleToPolicy(forms.SelfHandlingForm):
    firewall_rule_id = forms.ChoiceField(label=_("Insert Rule"))
    insert_before = forms.ChoiceField(label=_("Before"),
                                      required=False)
    insert_after = forms.ChoiceField(label=_("After"),
                                     required=False)

    failure_url = 'horizon:project:firewalls:index'

    def __init__(self, request, *args, **kwargs):
        super(InsertRuleToPolicy, self).__init__(request, *args, **kwargs)

        try:
            tenant_id = self.request.user.tenant_id
            all_rules = api.fwaas.rule_list_for_tenant(request, tenant_id)
            all_rules = sorted(all_rules, key=lambda rule: rule.name_or_id)

            available_rules = [r for r in all_rules
                               if not r.firewall_policy_id]

            current_rules = []
            for r in kwargs['initial']['firewall_rules']:
                r_obj = [rule for rule in all_rules if r == rule.id][0]
                current_rules.append(r_obj)

            available_choices = [(r.id, r.name_or_id) for r in available_rules]
            current_choices = [(r.id, r.name_or_id) for r in current_rules]

        except Exception as e:
            msg = _('Failed to retrieve available rules: %s') % e
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)

        self.fields['firewall_rule_id'].choices = available_choices
        self.fields['insert_before'].choices = [('', '')] + current_choices
        self.fields['insert_after'].choices = [('', '')] + current_choices

    def handle(self, request, context):
        policy_id = self.initial['policy_id']
        policy_name_or_id = self.initial['name'] or policy_id
        try:
            insert_rule_id = context['firewall_rule_id']
            insert_rule = api.fwaas.rule_get(request, insert_rule_id)
            body = {'firewall_rule_id': insert_rule_id,
                    'insert_before': context['insert_before'],
                    'insert_after': context['insert_after']}
            policy = api.fwaas.policy_insert_rule(request, policy_id, **body)
            msg = _('Rule %(rule)s was successfully inserted to policy '
                    '%(policy)s.') % {
                        'rule': insert_rule.name or insert_rule.id,
                        'policy': policy_name_or_id}
            LOG.debug(msg)
            messages.success(request, msg)
            return policy
        except Exception as e:
            msg = _('Failed to insert rule to policy %(name)s: %(reason)s') % {
                'name': policy_id, 'reason': e}
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)


class RemoveRuleFromPolicy(forms.SelfHandlingForm):
    firewall_rule_id = forms.ChoiceField(label=_("Remove Rule"))

    failure_url = 'horizon:project:firewalls:index'

    def __init__(self, request, *args, **kwargs):
        super(RemoveRuleFromPolicy, self).__init__(request, *args, **kwargs)

        try:
            tenant_id = request.user.tenant_id
            all_rules = api.fwaas.rule_list_for_tenant(request, tenant_id)

            current_rules = []
            for r in kwargs['initial']['firewall_rules']:
                r_obj = [rule for rule in all_rules if r == rule.id][0]
                current_rules.append(r_obj)

            current_choices = [(r.id, r.name_or_id) for r in current_rules]
        except Exception as e:
            msg = _('Failed to retrieve current rules in policy %(name)s: '
                    '%(reason)s') % {'name': self.initial['name'], 'reason': e}
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)

        self.fields['firewall_rule_id'].choices = current_choices

    def handle(self, request, context):
        policy_id = self.initial['policy_id']
        policy_name_or_id = self.initial['name'] or policy_id
        try:
            remove_rule_id = context['firewall_rule_id']
            remove_rule = api.fwaas.rule_get(request, remove_rule_id)
            body = {'firewall_rule_id': remove_rule_id}
            policy = api.fwaas.policy_remove_rule(request, policy_id, **body)
            msg = _('Rule %(rule)s was successfully removed from policy '
                    '%(policy)s.') % {
                        'rule': remove_rule.name or remove_rule.id,
                        'policy': policy_name_or_id}
            LOG.debug(msg)
            messages.success(request, msg)
            return policy
        except Exception as e:
            msg = _('Failed to remove rule from policy %(name)s: '
                    '%(reason)s') % {'name': self.initial['name'],
                                     'reason': e}
            LOG.error(msg)
            redirect = reverse(self.failure_url)
            exceptions.handle(request, msg, redirect=redirect)
