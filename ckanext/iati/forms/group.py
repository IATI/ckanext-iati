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
from ckan.forms.common import TextExtraField
from ckan.lib.helpers import literal

__all__ = ['get_group_dict', 'edit_group_dict']



def build_group_form(is_admin=False, with_packages=False):
    
    PUBLISHER_TYPES = [_("Donor"),
                       _("Recipient"),
                       _("Community")]

    publisher_record_fields = (('publisher_contact',
                               'Contact',
                               'Email or URL for publisher'),
                               ('publisher_description',
                               'Description',
                               "General description of Publisher's role and activities"),
                               ('publisher_agencies',
                               'Organisations / agencies covered',
                               'Whose activities does this publisher publish?'),
                               ('publisher_timeliness',
                               'Timeliness of Data',
                               'How up do date is the data when published?'),
                               ('publisher_frequency',
                               'Frequency of publication',
                               'How often is IATI data refreshed?  Monthly/Quarterly?'),
                               )
    
    builder = FormBuilder(model.Group)
    builder.set_field_text('name', 'Unique Name (required)', 
            literal("<br/><strong>Unique identifier</strong> for group.<br/>2+ chars, lowercase, using only 'a-z0-9' and '-_'"))
    builder.set_field_option('name', 'validate', common.group_name_validator)
    builder.set_field_option('state', 'dropdown', {'options':model.State.all})
    builder.add_field(SelectExtraField('type', options=PUBLISHER_TYPES, allow_empty=False))
    builder.set_field_text('type', 'Type')
    for name, title, description in publisher_record_fields:
        builder.add_field(TextExtraField(name))
        builder.set_field_text(name, title, description)

    displayed_fields = ['name', 'title', 'type',] + [x[0] for x in publisher_record_fields]
    
    from ckan.authz import Authorizer
    from ckan.lib.base import c
    if Authorizer.is_sysadmin(c.user):
        displayed_fields.append('state')

    
    if with_packages:
        builder.add_field(group.PackagesField('packages'))
        displayed_fields.append('packages')
    builder.set_displayed_fields(OrderedDict([('Details', displayed_fields)]))
    builder.set_label_prettifier(common.prettify)
    return builder  

def get_group_fieldset(is_admin=False, combined=False):
    return build_group_form(is_admin=is_admin, with_packages=combined).get_fieldset()
   
