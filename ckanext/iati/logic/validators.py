from urlparse import urlparse, urlunparse
from dateutil.parser import parse as date_parse
from datetime import datetime
from email_validator import validate_email
import re
from sqlalchemy import and_
from ckan.logic import get_action
from ckan import authz as new_authz
from ckan.lib.navl.dictization_functions import unflatten, Invalid
from ckanext.iati.lists import FILE_TYPES, COUNTRIES
from ckanext.iati import model as iati_redirects
from ckan.lib.navl.dictization_functions import StopOnError, missing
from ckan.common import _
import ckan.plugins as p
import ckanext.iati.emailer as emailer

def iati_one_resource(key, data, errors, context):

    if not ('resources', 0, 'url') in data:
        raise Invalid('Datasets must have one resource (a link to an IATI XML file)')

def iati_resource_count(key, data, errors, context):
    if len(key) > 1 and key[1] > 0:
        errors[key].append('Datasets can only have one resource (a single IATI XML file)')


def send_url_invalid_email(context, is_url_error=True):
    user = context['auth_user_obj']
    if is_url_error:
        body = emailer.data_has_url_errors.format(
            user_name=context['user'], publisher_name='publisher_name',
            publisher_registry_dataset_link='publisher_registry_dataset_link'
        )
    else:
        body = emailer.data_not_xml_email_body.format(
            user_name=context['user'], publisher_name='publisher_name',
            publisher_registry_dataset_link='publisher_registry_dataset_link'
        )

    subject = "Invalid dataset upload format"
    emailer.send_email(body, subject, user.email, content_type='html')


def iati_resource_url(value, context, is_dataset_url=False):
    if not value:
        return

    try:
        url = urlparse(value)
    except ValueError:
        raise Invalid('Invalid URL')

    valid_schemes = ('http', 'https', 'ftp')
    if not url.scheme in valid_schemes:
        send_url_invalid_email(context)
        raise Invalid('Invalid URL scheme')
    if not url.hostname:
        send_url_invalid_email(context)
        raise Invalid('Invalid URL host name')
    if is_dataset_url and not value.endswith('.xml'):
        send_url_invalid_email(context, is_url_error=False)
        raise Invalid("Incorrect file format. All files should be in XML format that follows the IATI Standard. See http://iatistandard.org/")

    value = urlunparse(url)

    return value

def iati_resource_url_mandatory(value, context):

    value = iati_resource_url(value, context, True)

    if (not value) or (not value.strip()):
        raise Invalid('URL cannot be empty')
    return value

def iati_owner_org_validator(key, data, errors, context):

    value = data.get(key)
    if value:
        model = context['model']
        group = model.Group.get(value)
        if group.state != 'active':
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
        org_key = ("owner_org", )
        errors[org_key] = errors.get("owner_org", [])
        errors[org_key].append('Publisher name missing. Please select a publisher from the list.')
        return

    org = get_action('organization_show')(context,{'id': unflattened['owner_org']})
    org_name = org['name']

    org_regex = re.compile(r'{org_name}-{any_code}'.format(
      org_name=re.escape(org_name),
      any_code='.+'
    ))

    if not org_regex.match(value):
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

def db_date(value, context):

    try:
        value = date_parse(value)
    except (ValueError, e):
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

def email_validator(key, data, errors, context):
    email = data[key]

    try:
        v = validate_email(email, check_deliverability=False)
    except Exception as e:
        errors[key].append('Please provide a valid email address. The email address should be for a mailbox that is regularly monitored.')


def iati_org_identifier_validator(key, data, errors, context):
    """
    Enforce unique IATI IDs.

    If an IATI ID does exist and it doesn't belong to the publisher submitting
    the form or making the API request, throw a validation error.

    Both `name` and `publisher_iati_id` must be unique (though `name` ==
    `publisher_iati_id` is possible); users must be able to change them
    independently of one another.
    """
    model = context['model']
    session = context['session']
    group = context.get('group')
    publisher_iati_id = data[key]
    user = context.get('user')

    if group:
        group_id = group.id
    else:
        group_id = data.get('id')

    # check if the IATI ID exists
    publisher_id_exists = session.query(model.Group)\
        .join((model.GroupExtra, model.Group.id == model.GroupExtra.group_id))\
        .filter(and_(model.GroupExtra.value == publisher_iati_id, model.GroupExtra.key == 'publisher_iati_id')).first()

    
    # if the ID exists and it doesn't belong to the org submitting the form
    # or the API request, block it
    if publisher_id_exists and ( publisher_id_exists.state != "deleted") and (publisher_id_exists.id != group_id):
        errors[key].append('IATI identifier already exists. Please verify if your organisation already has a publisher account.')


def remove_leading_or_trailing_spaces(value,context):
    return value.strip()


def licence_validator(key, data, errors, context):
    """ Validates the licence. License made mandatory field while creating a
        new publisher"""

    licenses = get_action('license_list')(context)

    licenses_list = [license['id'] for license in licenses]
    
    if (data[key] not in licenses_list) or (data[key] == 'lc_notspecified'):
        errors[key].append('Please specify the License.')


def _check_access_to_change_ids(key, data, group, user):

    if isinstance(key, tuple):
        key_comp = key[0]

    if key_comp =='publisher_iati_id':
        val = group.extras.get('publisher_iati_id', '')
    elif key_comp == 'name':
        val = group.name

    if val and val != data.get(key) and group.state == 'active':
        if not new_authz.is_sysadmin(user):
            return False
    return True


def change_publisher_id_or_org_id(key, data, errors, context):

    group = context.get('group')
    user = context.get('user')

    if group:
        if not _check_access_to_change_ids(key, data, group, user):
            errors[key].append('Only system admin can change this {} for an active dataset.'.format(key[0]))


def first_publisher_date_validator(key, data, errors, context):

    given_date = data[key]
    if given_date:
        try:
            # If the given date format is YYYY-MM-DD convert to ISO format
            datetime.strptime(given_date, "%Y-%m-%dT%H:%M:%S.%f").isoformat()
        except ValueError:
            errors[key].append("Incorrect date format. Pleas enter date in format YYYY-MM-DD")


def validate_date(key, data_dict):
    """
    Validate the date format
    :param key: from_dt or to_dt
    :param data_dict: dict
    :param errors: dict
    :return: raises error
    """
    if not data_dict.get(key):
        raise ValueError
    date_parse(data_dict.get(key))


def check_date_period(data_dict, errors, limit=732):
    """
    Check the dates from and two dates. Max Allowed period is only for 24 months period.
    :param data_dict: dict
    :param errors: dict
    :param limit: no of days (6 months nearly 182 days)
    :return: errors
    """

    from_dt = date_parse(data_dict.get('from_dt'))
    to_dt = date_parse(data_dict.get('to_dt'))
    if from_dt >= to_dt:
        errors['from_dt'] = ["From date greater than to date"]
        return errors

    _period = (from_dt - to_dt).days

    if _period > limit:
        errors['from_dt'] = ["Exceeded the limit"]
        errors['to_dt'] = ["Exceeded the limit"]
        return errors

    return errors


def validate_new_publisher_id_against_old(key, data, errors, context):
    """
    Validate if the given publisher id is one of the old publisher id. If so, raise an error.
    All the old publisher id will be available in iati_redirects table,, which should be update by
    sysadmin regularly through UI.

    :param key: str publisher_iati_id
    :param data: dict
    :param errors: dict (error dict)
    :return: None (Raises error if the id exists)
    """
    session = context['session']
    _iati_piublisher_id = data.get(key, '').strip()
    if _iati_piublisher_id:
        publisher_id_exists = session.query(iati_redirects.IATIRedirects).filter(
            iati_redirects.IATIRedirects.old_name == _iati_piublisher_id).first()
        if publisher_id_exists:
            errors[key].append("Publisher Id is already exists. Please try with another id.")


def not_missing(key, data, errors, context):

    value = data.get(key)
    if value is missing:
        errors[key].append(_('Please fill required field'))
        raise StopOnError

def not_empty(key, data, errors, context):

    value = data.get(key)
    if not value or value is missing:
        errors[key].append(_('Please fill required field'))
        raise StopOnError


def iati_publisher_name_validator(value, context):
    try:
        return p.toolkit.get_validator('name_validator')(value, context)
    except Invalid:
        raise Invalid("This will be the unique identifier for the publisher. "
                      "Where possible use a short abbreviation of your organisation's name. "
                      "For example: 'dfid' or 'worldbank' Must be at least two characters long and lower case. "
                      "Can include letters, numbers and also - (dash) and _ (underscore).")

def iati_org_identifier_name_validator(value, context):
    name_match = re.compile(r'[a-zA-Z0-9_.-]*$')
    if not name_match.match(value):
        raise Invalid(_('Invalid character detected. Valid character includes letter, numbers, . and - (dash).'))
    return value

