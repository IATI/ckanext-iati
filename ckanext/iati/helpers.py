import urllib
import os
from xml.etree import ElementTree
import datetime
import json
from markupsafe import Markup, escape
from sqlalchemy import create_engine
# Bad import: should be in toolkit
from pylons import config
from webhelpers.html import literal
import ckan.authz as authz
import ckan.model as model # get_licenses should be in core
from ckan.model import User
import ckan.lib.dictization.model_dictize as model_dictize
import ckan.plugins as p
import ckan.lib.helpers as helpers
import ckan.lib.formatters as formatters
from ckan.logic import check_access, NotAuthorized
import ckanext.iati.lists as lists
import ckan.logic as logic
from ckan.common import c
from ckanext.dcat.processors import RDFSerializer
from collections import OrderedDict
from email_validator import validate_email as _validate_email
import logging
log = logging.getLogger(__name__)
    

def get_countries():
    countries = (("", u"(No country assigned)"),)
    get_countries_path = lambda: os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                              'countries.xml')
    root = ElementTree.parse(get_countries_path()).getroot()

    for item in root.find('codelist-items').iter():
        if item.tag == 'codelist-item':
            code = item.find('code').text
            name = item.find('name').find('narrative').text

            countries += (code, name),

    return countries

def get_publisher_source_types():
    return lists.PUBLISHER_SOURCE_TYPES

def get_publisher_frequencies():
    return lists.PUBLISHER_FREQUENCIES

def get_organization_types():
    return lists.ORGANIZATION_TYPES

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
        'publisher_country': get_country_title,
    }

    for ex in group_dict.get("extras", []):
        if ex.get("key", None) in formatter_map.keys():
            extras[ex["key"]] = formatter_map[ex["key"]](ex.get("value", ""))
    return extras

def get_publisher_obj_extra_fields_pub_ids(group_dict):
    extras = {}
    if not group_dict:
        return extras

    formatter_map = {
        'publisher_organization_type': get_organization_type_title,
        'publisher_country': get_country_title,
    }
    for ex in group_dict:
        if ex in formatter_map.keys():
            extras[ex] = formatter_map[ex](group_dict.get(ex, ""))
    dict_extras = extras_to_dict(group_dict)

    extras['publisher_iati_id'] = group_dict['publisher_iati_id']
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
        options = get_publisher_source_types()
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
        options = get_organization_types()
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
    return urllib.quote(string)

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
        if not (facet, facet_item['name']) in p.toolkit.request.params.items():
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
        'facet.field': p.toolkit.c.facet_titles.keys()
    })
    return query['search_facets']

def normalize_publisher_name(name):

    if name[:4].lower() == 'the ':
        return name[4:] + ', The'
    return name

def organization_list():
    return p.toolkit.get_action('organization_list')({}, {'all_fields': True,
                                                          'sort': 'title asc'})


def organization_list_publisher_page():
    return p.toolkit.get_action('organization_list_publisher_page')({}, {
        'all_fields': True, 'sort': 'title asc', 'include_extras': True})


def organization_list_pending():

    if authz.is_sysadmin(c.user):
        return p.toolkit.get_action('organization_list_pending')({}, {
            'all_fields': True, 'sort': 'title asc', 'include_extras': True})
    else:
        return _pending_organization_list_for_user()


def get_first_published_date(organization):
    if 'publisher_contact_email' not in organization or not organization['publisher_contact_email']:
        organization.update({'publisher_contact_email': 'Email not found'})
    try:
        publisher_first_publish_date = organization['publisher_first_publish_date']
        if publisher_first_publish_date == '':
            raise KeyError
        else:
            return publisher_first_publish_date
    except KeyError:
        date_not_found_error = 'Date not found'

        # Setup for search, since package_search action returns the first
        # 1000 rows by default.
        dates = []
        data_dict = {
            'fq': 'organization:{}'.format(organization['name']),
            'rows': 1000
        }

        package_search_results = p.toolkit.get_action('package_search')(
            {}, data_dict=data_dict)['results']

        if len(package_search_results) == 0:
            return 'No data published'

        for package in package_search_results:
            try:
                resource_created_date = package['resources'][0]['created']
            except:
                continue

            dates.append(resource_created_date)

        if len(dates) == 0:
            return date_not_found_error

        publisher_first_publish_date = sorted(dates)[0]

        if not publisher_first_publish_date:
            return date_not_found_error

        data_dict = {
            'id': organization['id'],
            'publisher_first_publish_date':
                publisher_first_publish_date
        }

        '''try:
            check_access('organization_patch', {})
            p.toolkit.get_action('organization_patch')({}, data_dict=data_dict)
        except NotAuthorized:
            pass'''

        return publisher_first_publish_date


def render_first_published_date(value, date_format='%d %B %Y'):

    try:
        if len(value) <= 10:
            current_date_format = '%Y-%m-%d'
        else:
            current_date_format = '%Y-%m-%dT%H:%M:%S.%f'

        return datetime.datetime.strptime(value, current_date_format).strftime(date_format)
    except ValueError:
        return 'Date is not valid'


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

        '''try:
            check_access('organization_patch', {})
            p.toolkit.get_action('organization_patch')({}, data_dict=data_dict)
        except NotAuthorized:
            pass'''

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


def publisher_first_published_date_validator(data_dict):
    """  This is the patch if first published date is empty take first resource date.
     which was done previously during read phase and it is inconsistent.
     This can be done through helper function 'first_published_date_patch'. But,
     Looks like organization_patch dosen't work while updating the organization and avoid multiple organization_show,
      """
    try:
        invalid_dates = ['No data published', 'Date not found', 'Date is not valid', '']
        first_pub_date = data_dict.get('publisher_first_publish_date', '')
        if not first_pub_date or (first_pub_date in invalid_dates) or (first_pub_date is None):
            first_pub_date = get_first_published_date(data_dict)
        else:
            try:
                datetime.datetime.strptime(first_pub_date, "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                _date = datetime.datetime.strptime(first_pub_date, "%Y-%m-%d")
                first_pub_date = _date.strftime("%Y-%m-%dT%H:%M:%S.%f")

        if str(first_pub_date).strip() not in invalid_dates:
            data_dict['publisher_first_publish_date'] = first_pub_date
    except Exception, e:
        print(e)
        log.warning("Cannot get the first published date - {}", str(e))

    return data_dict


def first_published_date_patch(org_id):
    """ This is the patch for publisher first published date - this patches the organization when
    new public package is created. Alos updates date to db if it is empty while updating the package
    e.g private to public or if the date is empty when resource,
    this will be throwing error for editors who do not have writes to update organization. This error can be ignored"""
    try:
        organization = p.toolkit.get_action('organization_show')({}, {'id': org_id})

        organization = publisher_first_published_date_validator(organization)

        data_dict = {
            'id': organization['id'],
            'publisher_first_publish_date': organization['publisher_first_publish_date']
        }

        try:
            check_access('organization_patch', {})
            p.toolkit.get_action('organization_patch')({}, data_dict=data_dict)
        except NotAuthorized:
            pass
    except Exception, e:
        log.warning("Cannot be patched - {}", e)


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
    _link = "/publisher/download_list/{}"
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

