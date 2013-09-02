# Bad import: should be in toolkit
import ckan.model as model # get_licenses should be in core


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

