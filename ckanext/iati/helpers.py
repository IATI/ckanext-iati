# Bad import: should be in toolkit
from pylons import config
from webhelpers.html import literal

import ckan.model as model # get_licenses should be in core

import ckan.plugins as p
import ckan.lib.helpers as helpers
import ckan.lib.formatters as formatters

import ckanext.iati.lists as lists


def get_countries():
    return lists.COUNTRIES

def get_publisher_source_types():
    return lists.PUBLISHER_SOURCE_TYPES

def get_organization_types():
    return lists.ORGANIZATION_TYPES

def get_country_title(code):
    return _get_list_item_title(lists.COUNTRIES, code)

def get_file_type_title(code):
    return _get_list_item_title(lists.FILE_TYPES, code)

def get_publisher_source_type_title(code):
    return _get_list_item_title(lists.PUBLISHER_SOURCE_TYPES, code)

def get_organization_type_title(code):
    return _get_list_item_title(lists.ORGANIZATION_TYPES, code)

def get_issue_title(code):
    return code.replace('-', ' ').title()

def get_licenses():
    return [('', '')] + model.Package.get_license_options()

def get_publisher_organization_type(group_id):
    group = model.Group.get(group_id)
    if group:
        org_type = group.extras.get('publisher_organization_type')
        if org_type:
            return get_organization_type_title(org_type)
    return ''

def is_route_active(menu_item):
    _menu_items = config.get('routes.named_routes')
    if menu_item not in _menu_items:
        return False
    return helpers._link_active(_menu_items[menu_item])

def return_select_options(name, data):
    return_options = []
    return_selected = False

    if name == 'publisher_type':
        options = get_publisher_source_types()
        return_selected = data.get('type')
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
    if p.toolkit.c.search_facets_limits:
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
