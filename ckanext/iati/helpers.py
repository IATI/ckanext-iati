import urllib.request, urllib.parse, urllib.error
import os
import time
from xml.etree import ElementTree
import datetime
import json
from markupsafe import Markup, escape
from sqlalchemy import create_engine
from webhelpers2.html import literal
import ckan.authz as authz
import ckan.model as model # get_licenses should be in core
from ckan.model import User
import ckan.lib.dictization.model_dictize as model_dictize
import ckan.plugins as p
from ckan.plugins.toolkit import config
import ckan.lib.helpers as helpers
import ckan.lib.formatters as formatters
from ckan.logic import check_access, NotAuthorized, ValidationError
import ckanext.iati.lists as lists
import ckan.logic as logic
from ckan.common import c
from ckanext.dcat.processors import RDFSerializer
from collections import OrderedDict
from email_validator import validate_email as _validate_email
from dateutil.parser import parse as dt_parse
import uuid
import logging
from ckanext.iati.countries import COUNTRIES
log = logging.getLogger(__name__)
    

def get_countries():
    countries = (("", "Please select"),)
    get_countries_path = lambda: os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                              'countries.xml')
    root = ElementTree.parse(get_countries_path()).getroot()

    for item in root.find('codelist-items').iter():
        if item.tag == 'codelist-item':
            code = item.find('code').text
            name = item.find('name').find('narrative').text

            countries += (code, name),

    return countries

def get_publisher_source_types(add_default_empty=False):
    options = lists.PUBLISHER_SOURCE_TYPES[:]
    if add_default_empty:
        options.insert(0, ("", "Please select"))
    return options

def get_publisher_frequencies():
    return lists.PUBLISHER_FREQUENCIES

def get_organization_types(add_default_empty=False):
    options = lists.ORGANIZATION_TYPES[:]
    if add_default_empty:
        options.insert(0, ("", "Please select"))
    return options

def get_country_title(code):
    return _get_list_item_title(lists.COUNTRIES, code)

def get_file_type_title(code):
    return _get_list_item_title(lists.FILE_TYPES, code)

def get_publisher_source_type_title(code):
    return _get_list_item_title(lists.PUBLISHER_SOURCE_TYPES, code)

def get_publisher_frequency_title(code):
    return _get_list_item_title(lists.PUBLISHER_FREQUENCIES, code)

def get_organization_type_title(code):
    return _get_list_item_title(lists.ORGANIZATION_TYPES, code)

def get_issue_title(code):
    return code.replace('-', ' ').title()

def get_licenses():
    return [('', '')] + model.Package.get_license_options()


def organizations_available_with_extra_fields(permission='manage_group', include_dataset_count=True):

    ''' Return a list of organizations that the current user has the specified permission for. '''

    context = {'user': c.user}
    data_dict = {
        'permission': permission,
        'include_dataset_count': include_dataset_count}
    organizations = logic.get_action('organization_list_for_user')(context, data_dict)
    org_extra = []

    for organization in organizations:

        extras = get_publisher_extra_fields(organization['id'])

        for key in extras:
            organization[key] = extras[key]
        org_extra.append(organization)
    return organizations


def get_publisher_extra_fields(group_id):
    group = model.Group.get(group_id)
    extras = {}
    if not group:
        return extras
    for extra, formatter in [
        ('publisher_organization_type', get_organization_type_title,),
        ('publisher_country', get_country_title,)
    ]:
        extras[extra] = formatter(group.extras.get(extra))
    return extras

def get_publisher_obj_extra_fields(group_dict):
    extras = {}
    if not group_dict:
        return extras

    formatter_map = {
        'publisher_organization_type': get_organization_type_title,
        'publisher_country': get_country_title
    }

    for ex in group_dict.get("extras", []):
        if ex.get("key", None) in formatter_map.keys():
            extras[ex["key"]] = formatter_map[ex["key"]](ex.get("value", ""))
    return extras

def get_publisher_obj_extra_fields_pub_ids(group_dict):
    extras = {}
    if not group_dict:
        log.info('not group_dict')
        return extras

    formatter_map = {
        'publisher_organization_type': get_organization_type_title,
        'publisher_country': get_country_title,
        'publisher_first_publish_date': render_first_published_date_parse
    }
    for ex in group_dict:
        if ex in formatter_map.keys():
            extras[ex] = formatter_map[ex](group_dict.get(ex, ""))

    extras['publisher_iati_id'] = group_dict.get('publisher_iati_id', '')
    return extras

def _user_last_activity(user):
    q = model.Session.query(model.Activity)
    q = q.filter(model.Activity.user_id == user[0].id)
    q = q.order_by(model.Activity.timestamp.desc())

    last_activity = q.first()
    if last_activity:
        return last_activity.timestamp.strftime("%d %b %Y")
    else:
        return ''

def _user_publishers(user):
    # Group = IATI Publisher
    publisher = model.Group
    query = model.Session.query(publisher) \
        .join(model.Member, (publisher.id == model.Member.group_id)) \
        .filter(model.Member.table_id == user[0].id)
    return query.all()

def get_user_search_extras(user):
    extras = {}
    if not user:
        return extras
    extras['publishers'] = _user_publishers(user)
    extras['last_activity'] = _user_last_activity(user)
    return extras

def is_route_active(menu_item):
    _menu_items = config.get('routes.named_routes')
    if menu_item not in _menu_items:
        return False
    return helpers._link_active(_menu_items[menu_item])

def return_select_options(name, data):
    return_options = []
    return_selected = False

    if name == 'publisher_source_type':
        options = get_publisher_source_types(add_default_empty=True)
        return_selected = data.get('publisher_source_type')
        for value, label in options:
            return_options.append({ 'text': label, 'value': value })
    if name == 'publisher_frequency_select':
        options = get_publisher_frequencies()
        return_selected = data.get('publisher_frequency_select')
        for value, label in options:
            return_options.append({ 'text': label, 'value': value })
    elif name == 'license_id':
        options = get_licenses()
        return_selected = data.get('license_id', 'notspecified')
        for label, value in options:
            if label:
                return_options.append({ 'text': label, 'value': value })
    elif name == 'publisher_organization_type':
        options = get_organization_types(add_default_empty=True)
        return_selected = data.get('publisher_organization_type')
        for value, label in options:
            return_options.append({ 'text': label, 'value': value })
    elif name == 'state':
        return_options = [
            { 'text': 'Active', 'value': 'active' },
            { 'text': 'Pending', 'value': 'approval_needed' },
            { 'text': 'Deleted', 'value': 'deleted' },
        ]
        return_selected = data.get('state', 'none')

    return (return_options, return_selected)

def get_config_option(key):
    return config.get(key)

def _get_list_item_title(_list, code):
    return dict(_list).get(code, code)

def check_nav_dropdown(items):
    return_items = []
    if items:
        for item in items:
            if (item[0]):
                return_items.append(item)
    if return_items:
        return return_items
    return False

def get_num_active_publishers():
    data_dict = {
        'q':'*:*',
        'facet.field': ['organization', 'country'],
        'facet.limit': 10000,
        'rows':0,
        'start':0,
    }

    query = p.toolkit.get_action('package_search')({} , data_dict)

    num_publishers = len(query['search_facets']
                         .get('organization', [])
                         .get('items', []))
    return num_publishers

def SI_number_span(number):
    ''' outputs a span with the number in SI unit eg 14700 -> 14.7k '''
    number = int(number)
    if number < 1000:
        output = literal('<span>')
    else:
        output = literal('<span title="' + formatters.localised_number(number) + '">')
    return output + formatters.localised_SI_number(number) + literal('</span>')

def format_file_size(size):
    if size is None:
        return None
    try:
        size = float(size)
    except ValueError:
        return None

    for label in ['bytes','KB','MB','GB','TB']:
        if size < 1024.0:
            return "%3.1f %s" % (size, label)
        size /= 1024.0

def urlencode(string):
    # Jinja 2.7 has this filter directly available
    return urllib.parse.quote(string)

def extras_to_dict(pkg):
    extras_dict = {}
    if pkg and 'extras' in pkg:
        for extra in pkg['extras']:
            extras_dict[extra['key']] = extra['value']
    return extras_dict

def extras_to_list(extras):
    extras_list = []
    for key in extras:
        extras_list.append(dict(key=key, value=extras[key]))
    return extras_list

def publishers_pagination(q):
    '''
        Hack alert: the group controller does not currently offer a way to
        customize the pagination links (we need a proper IGroupForm interface
        with types support), so on the meantime we tweak the output of the
        default pagination
    '''
    return p.toolkit.c.page.pager(q=q).replace('organization', 'publisher')

def get_global_facet_items_dict(facet, limit=10, exclude_active=False, search_facets=None):
    '''
        Modified version of get_facet_items_dict that allows facets to be
        passed as params as opposed to always use the ones on c.

    '''
    if not search_facets:
        search_facets = p.toolkit.c.search_facets

    if not search_facets or \
            not search_facets.get(facet) or \
            not search_facets.get(facet).get('items'):
        return []

    facets = []
    for facet_item in search_facets.get(facet)['items']:
        if not len(facet_item['name'].strip()):
            continue
        if not (facet, facet_item['name']) in list(p.toolkit.request.params.items()):
            facets.append(dict(active=False, **facet_item))
        elif not exclude_active:
            facets.append(dict(active=True, **facet_item))
    facets = sorted(facets, key=lambda item: item['count'], reverse=True)
    if not limit and p.toolkit.c.search_facets_limits:
        limit = p.toolkit.c.search_facets_limits.get(facet)
    if limit:
        return facets[:limit]
    else:
        return facets

def get_global_search_facets():

    query = p.toolkit.get_action('package_search')({}, {
        'q': '*:*',
        'facet.field': list(p.toolkit.c.facet_titles.keys())
    })
    return query['search_facets']

def normalize_publisher_name(name):

    if name[:4].lower() == 'the ':
        return name[4:] + ', The'
    return name

def organization_list(include_extras=True):
    data_dict = {'all_fields': True, 'sort': 'title asc'}
    if include_extras:
        data_dict['include_extras'] = include_extras
    return p.toolkit.get_action('organization_list')({}, data_dict)

def organization_list_pending(q=None):
    context = {'user': c.user, "model": model}
    if authz.is_sysadmin(c.user):
        return p.toolkit.get_action('organization_list_pending')(context, {
            'all_fields': True, 'q': q, 'sort': 'title asc', 'include_extras': True})
    else:
        return _pending_organization_list_for_user()

def is_string_uuid(val):
    """
    Checks if the given string is a valid UUID
    :param val: str
    :return: boolean
    """
    if val and isinstance(val, str):
        try:
            uuid.UUID(val)
            return True
        except ValueError:
            pass

    return False


def get_first_published_date(organization):
    """
    Get first publisher date from an organization. Check if the date is invalid, get the date
    :param organization:
    :return:
    """
    _invalid_dates = ('No data published', 'Date not found', 'Date is not valid')

    # Check if publisher date already exists. return the existing date - do not modify
    org_pub_date = organization.get('publisher_first_publish_date', '')
    if org_pub_date and org_pub_date.strip() and (org_pub_date  not in _invalid_dates):
        return org_pub_date

    org_id = organization.get('id', '')

    if is_string_uuid(org_id):
        fq = 'owner_org:{}'.format(organization['id'])
    else:
        fq = 'organization:{}'.format(organization['name'])

    pkg_search_results = p.toolkit.get_action('package_search')(
        {}, data_dict={'fq': fq, 'rows': 1000}).get('results', [])

    if not pkg_search_results:
        return ''

    first_date = ''
    for pkg in pkg_search_results:
        # For IATI one package can have only one resource
        resc_date = pkg.get('metadata_created', '') or pkg.get('metadata_modified', '')
        if resc_date:
            try:
                if not first_date:
                    first_date = resc_date
                else:
                    if dt_parse(resc_date) < dt_parse(first_date):
                        first_date = resc_date
            except ValueError as e:
                log.info("First published date parse error")
                log.error(e)
    return first_date


def render_first_published_date(value, date_format='%d %B %Y'):

    try:
        if len(value) <= 10:
            current_date_format = '%Y-%m-%d'
        else:
            current_date_format = '%Y-%m-%dT%H:%M:%S.%f'

        return datetime.datetime.strptime(value, current_date_format).strftime(date_format)
    except ValueError:
        return 'Date is not valid'


def render_first_published_date_parse(value, date_format='%d %B %Y', default_value='NA/Incorrect format'):

    if not value:
        return default_value

    try:
        value = dt_parse(value)
        return value.strftime(date_format)
    except Exception as e:
        log.error(e)
        return default_value

def dataset_follower_count(context, data_dict):
    return  p.toolkit.get_action('dataset_follower_count')({}, data_dict=data_dict)


def radio(selected, id, checked):
    if checked == 'True':
        return literal(('<input checked="checked" type="radio" id="%s_%s" name="%s" value="%s">') % (selected, id, selected, id))
    return literal(('<input type="radio" id="%s_%s" name="%s" value="%s">') % (selected, id, selected, id))


def check_publisher_contact_email(organization):
    # publisher_contact_email was changed to be a required field
    # This function checks if the field is populated and fills an arbitrary value if empty
    if 'publisher_contact_email' not in organization or not organization['publisher_contact_email']:
        data_dict = {
            'id': organization['id'],
            'publisher_contact_email': 'please@update.email'
        }


        return data_dict['publisher_contact_email']
    else:
        return organization['publisher_contact_email']


def organizations_cntry_type_logged_user(permission='manage_group', include_dataset_count=False):

    '''Return a list of organizations that the current user has the specified
    permission for.
    '''

    context = {'user': c.user}
    data_dict = {
        'permission': permission,
        'include_dataset_count': include_dataset_count}
    organizations = logic.get_action('organization_list_for_user')(context, data_dict)
    #print(organizations)

    return None

def dcat_markup_dataset_show(context, data_dict):

    p.toolkit.check_access('dcat_dataset_show', context, data_dict)

    dataset_dict = p.toolkit.get_action('package_show')(context, data_dict)
    #print dataset_dict
    dataset_dict['notes'] = dataset_dict['title']
    #print dataset_dict

    serializer = RDFSerializer(profiles=data_dict.get('profiles'))

    output = serializer.serialize_dataset(dataset_dict,
                                          _format=data_dict.get('format'))

    return output

def structured_data_markup(dataset_id, profiles=None, _format='jsonld'):
    '''
    Returns a string containing the structured data of the given
    dataset id and using the given profiles (if no profiles are supplied
    the default profiles are used).
    This string can be used in the frontend.
    This function was orignally defined in dcat extension. But as in IATI 
    we have no descriptions of datasets, we simply have to add it manually here. 
    '''
    if not profiles:
        profiles = ['schemaorg']
    
    context = {'user': c.user}
    data =dcat_markup_dataset_show(
        context,
        {
            'id': dataset_id, 
            'profiles': profiles, 
            'format': _format, 
        }
    )
    # parse result again to prevent UnicodeDecodeError and add formatting
    try:
        json_data = json.loads(data)
        return json.dumps(json_data, sort_keys=True,
                          indent=4, separators=(',', ': '))
    except ValueError:
        # result was not JSON, return anyway
        return data


def email_validator(email):
    ''' Validates the given email '''
    try:
        _validate_email(email) 
        return True
    except Exception as e:
        return False

def get_user_list_by_email(value):
    """
    Get user id/name given email. Validate email beforehand.
    """
    users = []
    try:
        potential_users = User.by_email(value)
        return potential_users
    except Exception as e:
        log.error(e)
        return users


def first_published_date_patch(org_id):
    """
    This is the patch for publisher first published date - this patches the organization when
    new public package is created. Alos updates date to db if it is empty while updating the package
    e.g private to public or if the date is empty when resource,
    this will be throwing error for editors who do not have writes to update organization. This error can be ignored
    """
    if not config.get('iati.admin_user.name', ''):
        raise ValidationError("iati.admin_user.name config is not set")

    patch_dict = dict()
    _context = {
        "user": config.get('iati.admin_user.name'),
        "model": model
    }

    organization = p.toolkit.get_action('organization_show')({}, {'id': org_id})

    if 'publisher_contact_email' not in organization or not organization.get('publisher_contact_email', ''):
        # We need to patch the organization with email.
        # Other wise first publisher date patch fails
        patch_dict['publisher_contact_email'] = ['Email not found']

    org_first_published_date = organization.get('publisher_first_publish_date', '')
    calculated_date = get_first_published_date(organization)

    if calculated_date != org_first_published_date:
        patch_dict['publisher_first_publish_date'] = calculated_date

    if patch_dict:
        patch_dict['id'] = organization['id']
        try:
            p.toolkit.get_action('organization_patch')(_context, data_dict=patch_dict)
        except (ValidationError, NotAuthorized) as e:
            log.error(e)
        except Exception as e:
            log.error("First publisher date patch error id: {}".format(org_id))
            log.info(e)


def organization_form_read_only(data):
    """
    data contains most of the publisher data. However, for the first time it contains state of the dataset
    but if any validation error in the form, then data doest contain state. Hence, organization_show is necessary
    which is a quite an expensive process for the validation.
    """
    
    sysadmin = authz.is_sysadmin(c.user)
    attrs = {}
  
    if not sysadmin and data and data.get('state', '') == 'active':
       attrs = {'readonly':"readonly"}
    return attrs


def get_publisher_list_download_formats():

    formats = ('CSV', 'XLS', 'XML', 'JSON')
    _link = "/publisher/download/{}"
    downloads = OrderedDict()

    for _format in formats:
        downloads[_format] = _link.format(_format.lower())

    return downloads


def _pending_organization_list_for_user():

    """
    This will extract the pending publisher for the given user.
    :return: Pending Organizations
    """
    context = {'user': c.user, "model": model}
    user_obj = model.User.by_name(context.get('user'))
    try:
        q = model.Session.query(model.Member, model.Group) \
            .filter(model.Member.table_name == 'user') \
            .filter(model.Member.capacity == 'admin') \
            .filter(model.Member.table_id == user_obj.id) \
            .filter(model.Member.state == 'active') \
            .join(model.Group).all()

        _organizations = [_org.Group for _org in q if (_org.Group.state == "approval_needed" and
                                                       _org.Group.type == 'organization')]
        if _organizations:
            results = model_dictize.group_list_dictize(_organizations, context, include_extras=True)
        else:
            return []
        log.info("Total pending organizations for the user: {}".format(user_obj.id))
        log.info(len(results))
        return results
    except Exception as e:
        log.error("Unexpected error while getting pending organization for the user.")
        log.error("User id: {}".format(user_obj.id))
        log.error(e)

def get_archiver_status():
    """
    Fetches IATI-archiver last run timestamp. Timestamp is extracted from log file
    :return:
    """
    _archiver_log_filename = 'iati_archiver_2_out.log'
    _path = '/tmp'
    _full_path = os.path.join(_path, _archiver_log_filename)

    if os.path.isfile(_full_path):
        try:
            return str(time.ctime(os.path.getmtime(_full_path)))
        except Exception as e:
            log.error(e)
            return "Something wrong while parsing time. Please contact support team."
    else:
        return "Log file not available. Please contact support team"

def parse_error_object_to_list(error_object):
    """
    This is to parse if the error message is dictionary object - this scenario occurs from URL validator
    """
    error_list = []

    for element in error_object:
        if type(element) is dict:
            for key in element:
                error_list.append(str(element[key]))
        else:
            error_list.append(str(element))

    return error_list


def linked_user(user, maxlength=0, avatar=20):
    if not isinstance(user, model.User):
        user_name = helpers.text_type(user)
        user = model.User.get(user_name)
        if not user:
            return user_name
    if user:
        name = user.name if model.User.VALID_NAME.match(user.name) else user.id
        displayname = user.display_name

        if maxlength and len(user.display_name) > maxlength:
            displayname = displayname[:maxlength] + '...'

        if user.state == 'deleted' and not authz.is_sysadmin(c.user):
            return helpers.literal(helpers.text_type("Anonymous"))

        return helpers.literal('{icon} {link}'.format(
            icon=helpers.user_image(
                user.id,
                size=avatar
            ),
            link=helpers.link_to(
                displayname,
                helpers.url_for('user.read', id=name)
            )
        ))


def get_helper_text_popover_to_form(field_label, helper_text, is_required=False):
    """
    E.g. <a class="popover-link" href="javascript:void(0)" title="Description" data-toggle="popover"
            data-placement="top" data-html="true"  data-content="General description of publisher&#39;s
            role and activities."><i class="fa fa-question"></i></a>

    :param field_label:
    :param helper_text:
    :param is_required:
    :return:
    """

    helper_text = helper_text.replace("'", "&#39;")
    helper_text = helper_text.replace('"', "&#34;")

    link = """
        {field_label}
        <a class="popover-link" href="javascript:void(0)" title="{field_label}" data-toggle="popover"
            data-placement="top" data-html="true"  data-content="{helper_text}"><i class="fa fa-question"></i></a>
    """.format(field_label=field_label, helper_text=helper_text)

    if is_required:
        link = link+'<span class="required">*</span>'

    return link

def search_country_list():
    return [('', 'All')] + [(code, name) for code, name in COUNTRIES[1:]]

