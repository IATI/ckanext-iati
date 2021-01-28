from ckan.lib.navl.dictization_functions import Missing
from dateutil.parser import parse as dt_parse
from datetime import datetime
import logging
log = logging.getLogger(__name__)


def checkbox_value(value,context):

    return 'yes' if not isinstance(value, Missing) else 'no'


def strip(value, context):

    return value.strip()


def convert_date_string_to_iso_format(value, context):
    """
    Convert date time string to standard date time ISO format
    :param value:
    :param context:
    :return:
    """
    
    if value:
        try:
            # If the given date format is YYYY-MM-DD convert to ISO format
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f").isoformat()
        except ValueError:
            try:
                return datetime.strftime(dt_parse(value), "%Y-%m-%dT%H:%M:%S.%f")
            except Exception as e:
                log.error(e)
                pass

    return value

