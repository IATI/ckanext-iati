from ckan.logic import get_action
from ckan import new_authz
from ckan.lib.navl.dictization_functions import unflatten, Invalid
from ckan.lib.field_types import DateType, DateConvertError

from ckanext.iati.lists import FILE_TYPES, COUNTRIES



def iati_owner_org_validator(key, data, errors, context):

    value = data.get(key)

    model = context['model']
    group = model.Group.get(value)
    if not group.state == 'active':
        raise Invalid('Publisher must be active to add datasets to it')
    data[key] = group.id


def iati_publisher_state_validator(key, data, errors, context):
    user = context.get('user')

    if 'ignore_auth' in context:
        return

    if user and new_authz.is_sysadmin(user):
        return

    # If the user is not a sysadmin but we are creating the publisher,
    # we need to keep the state = pending value, otherwise ignore it.
    if not context.get('__iati_state_pending'):
        data.pop(key)


def iati_dataset_name(key,data,errors,context):

    unflattened = unflatten(data)
    value = data[key]

    if not unflattened.get('owner_org'):
         errors[key].append('Publisher name missing.' \
                 ' Please select a publisher from the list.')
         return

    org = get_action('organization_show')(context,{'id': unflattened['owner_org']})
    org_name = org['name']

    parts = value.split('-')
    code_part = parts[-1]
    group_part = parts[0] if len(parts) == 2 else '-'.join(parts[:-1])
    if not code_part or not group_part or not group_part == org_name:
        errors[key].append('Dataset name does not follow the convention <publisher>-<code>: "%s" (using publisher %s)' % (value, org_name))

def iati_dataset_name_from_csv(key,data,errors,context):

    unflattened = unflatten(data)
    value = data[key]

    if not unflattened.get('registry-publisher-id',None):
        errors[key].append('Publisher name missing')
        return

    # Ask for the group details to ensure it actually exists
    group = get_action('group_show')(context,{'id':unflattened['registry-publisher-id']})
    group_name = group['name']

    parts = value.split('-')
    code_part = parts[-1]
    group_part = parts[0] if len(parts) == 2 else '-'.join(parts[:-1])
    if not code_part or not group_part or not group_part == group_name:
        errors[key].append('Dataset name does not follow the convention <publisher>-<code>: "%s" (using publisher %s)' % (value,group_name))

def file_type_validator(key,data,errors, context=None):
    value = data.get(key)

    allowed_values = [t[0] for t in FILE_TYPES]
    if not value in allowed_values:
        errors[key].append('File type must be one of [%s]' % ', '.join(allowed_values))

def date_from_csv(value, context):
    try:
        # Try first with DD/MM/YYYY, etc
        value = DateType.form_to_db(value)
    except DateConvertError, e:
        # If not try YYYY-MM-DD
        try:
            value = db_date(value,context)
        except Invalid, e:
            if 'cannot parse' in e.error.lower():
                msg = "Cannot parse db date '%s'. Acceptable formats: 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD', 'YYYY-MM', 'YYYY' \
                        or 'DD/MM/YYYY HH:MM', 'DD/MM/YYYY', 'MM/YYYY'" % (value)
                raise Invalid(msg)
            raise e
    return value

def db_date(value, context):
    try:
        timedate_dict = DateType.parse_timedate(value, 'db')
    except DateConvertError, e:
        # Cannot parse
        raise Invalid(str(e))
    try:
        value = DateType.format(timedate_dict, 'db')
    except DateConvertError, e:
        # Values out of range
        raise Invalid(str(e))

    return value

def yes_no(value,context):

    value = value.lower()
    if not value in ['yes','no']:
        raise Invalid('Value must be one of [yes, no]')

    return value

def country_code(value,context):

    value = value.upper()
    if not value in [c[0] for c in COUNTRIES]:
        raise Invalid('Unknown country code "%s"' % value)

    return value

