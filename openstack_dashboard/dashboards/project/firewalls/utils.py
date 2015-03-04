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

from django.utils.translation import ugettext_lazy as _

from horizon import forms

from openstack_dashboard import api


def set_port_id_and_direction():
    if api.fwaas.get_firewall_provider():
        widget = None
        required = True
    else:
        widget = forms.HiddenInput()
        required = False
    port_id = forms.ChoiceField(label=_("Router Interface ID"),
                                required=required,
                                widget=widget)
    direction = forms.ChoiceField(label=_("Firewall Direction"),
                                  required=required,
                                  widget=widget)
    return port_id, direction
