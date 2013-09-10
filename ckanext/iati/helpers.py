# Bad import: should be in toolkit
from pylons import config

import ckan.model as model # get_licenses should be in core
import ckan.lib.helpers as helpers

import ckanext.iati.lists as lists

# TODO: Move the functions on patch.py and expose them via ITemplateHelpers,
# but only the ones that we need!

def get_countries():
    return lists.COUNTRIES

def get_publisher_source_types():
    return lists.PUBLISHER_SOURCE_TYPES

def get_organization_types():
    return lists.ORGANIZATION_TYPES

def get_licenses():
    return [('', '')] + model.Package.get_license_options()

def is_route_active(menu_item):
    _menu_items = config.get('routes.named_routes')
    if menu_item not in _menu_items:
        return False
    return helpers._link_active(_menu_items[menu_item])
