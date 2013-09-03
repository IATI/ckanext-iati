from ckan.lib.navl.dictization_functions import Missing


def checkbox_value(value,context):

    return 'yes' if not isinstance(value, Missing) else 'no'

def strip(value, context):

    return value.strip()
