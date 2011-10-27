from ckan.logic import get_action
from ckan.lib.navl.dictization_functions import unflatten

from ckanext.iati.lists import FILE_TYPES

def iati_dataset_name(key,data,errors,context):

    unflattened = unflatten(data)
    value = data[key]
    for grp in unflattened['groups']:
        if grp['id']:
            group_id = grp['id']
            break
    group = get_action('group_show')(context,{'id':group_id})
    group_name = group['name']

    parts = value.split('-')
    code_part = parts[-1]
    group_part = parts[0] if len(parts) == 2 else '-'.join(parts[:-1])
    if not code_part or not group_part or not group_part == group_name:
        errors[key].append('Dataset name does not follow the convention <publisher>-<code>: "%s" (using publisher %s)' % (value,group_name))

def iati_dataset_name_from_csv(key,data,errors,context):

    unflattened = unflatten(data)
    value = data[key]

    if not 'registry-publisher-id' in unflattened:
        errors[key].append('Publisher name missing')
        return

    group_name = unflattened['registry-publisher-id']

    parts = value.split('-')
    code_part = parts[-1]
    group_part = parts[0] if len(parts) == 2 else '-'.join(parts[:-1])
    if not code_part or not group_part or not group_part == group_name:
        errors[key].append('Dataset name does not follow the convention <publisher>-<code>: "%s" (using publisher %s)' % (value,group_name))

def file_type_validator(key,data,errors, context=None):
    value = data.get(key)

    allowed_values = [t[0] for t in FILE_TYPES] 
    if not value or not value in allowed_values:
        errors[key].append('File type must be one of [%s]' % ', '.join(allowed_values))


