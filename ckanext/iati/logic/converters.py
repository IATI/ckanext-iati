from ckan.lib.navl.dictization_functions import Missing

def convert_to_comma_list(value, context):

    return ', '.join(json.loads(value))

def convert_from_comma_list(value, context):

    return [x.strip() for x in value.split(',') if len(x)]

def checkbox_value(value,context):

    return 'yes' if not isinstance(value, Missing) else 'no'

def iso_date(value,context):
    from ckan.lib.field_types import DateType, DateConvertError
    try:
        value = DateType.iso_to_db(value)
    except DateConvertError, e:
        raise Invalid(str(e))
    return value

