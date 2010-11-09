import formalchemy
from formalchemy import helpers as fa_h
import ckan.lib.helpers as h

from ckan.forms.builder import FormBuilder
from sqlalchemy.util import OrderedDict
from pylons.i18n import _, ungettext, N_, gettext
import ckan.model as model
import ckan.forms.common as common
import ckan.forms.group as group
from ckan.forms.common import ExtrasField, PackageNameField, SelectExtraField
from ckan.lib.helpers import literal

__all__ = ['get_group_dict', 'edit_group_dict']



def build_group_form(is_admin=False, with_packages=False):
    
    PUBLISHER_TYPES = [_("Donor"),
                       _("Recipient"),
                       _("Community")]
    
    builder = FormBuilder(model.Group)
    builder.set_field_text('name', 'Unique Name (required)', literal("<br/><strong>Unique identifier</strong> for group.<br/>2+ chars, lowercase, using only 'a-z0-9' and '-_'"))
    builder.set_field_option('name', 'validate', common.group_name_validator)
    builder.set_field_option('state', 'dropdown', {'options':model.State.all})
    #builder.set_field_option('description', 'textarea', {'size':'60x15'})
    displayed_fields = ['name', 'title']
    if is_admin:
        builder.add_field(SelectExtraField('type', options=PUBLISHER_TYPES, allow_empty=False))
        builder.set_field_text('type', 'Type')
        displayed_fields.append('type')
        displayed_fields.append('state')
    #builder.add_field(ExtrasField('extras', hidden_label=True))
    
    if with_packages:
        builder.add_field(group.PackagesField('packages'))
        displayed_fields.append('packages')
    builder.set_displayed_fields(OrderedDict([('Details', displayed_fields)]))
    builder.set_label_prettifier(common.prettify)
    return builder  

fieldsets = {}

def get_group_fieldset(is_admin=False, combined=False):
    return build_group_form(is_admin=is_admin, with_packages=combined).get_fieldset()
   