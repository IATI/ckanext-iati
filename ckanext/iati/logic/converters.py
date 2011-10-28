from ckan.lib.navl.dictization_functions import Missing

def convert_to_comma_list(value, context):

    return ', '.join(json.loads(value))

def convert_from_comma_list(value, context):

    return [x.strip() for x in value.split(',') if len(x)]

def checkbox_value(value,context):

    return 'yes' if not isinstance(value, Missing) else 'no'

