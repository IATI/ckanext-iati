import logging
import re
import ckan.lib.helpers as h
import ckan.authz as authz
from ckan.lib.base import *
from ckan.model import Package

from ckanext.iati.controllers.group_schema import fields
from ckanext.iati.lists import ORGANIZATION_TYPES, COUNTRIES, PUBLISHER_SOURCE_TYPES, FILE_TYPES

log = logging.getLogger(__name__)

#########
log.warn("Monkey-patching package serialization format!")

# This needs to be done until the search indexing uses the logic
# functions (See #1352)

old_as_dict = Package.as_dict
def as_dict_with_groups_types(self):
#    import pdb; pdb.set_trace()
    _dict = old_as_dict(self)
    _dict['extras']['publishertype'] = ''.join([g.extras.get('type', '') for g in self.groups if g])
    return _dict

Package.as_dict = as_dict_with_groups_types

from ckan.lib.dictization import model_dictize
old_package_to_api1 = model_dictize.package_to_api1

def package_to_api1_with_groups_types(pkg,context):
    _dict = old_package_to_api1(pkg,context) 
    _dict['extras']['publishertype'] = ''.join([g.extras.get('type', '') for g in pkg.groups if g])
    return _dict

model_dictize.package_to_api1 = package_to_api1_with_groups_types

######### 



# TODO move this to helpers proper
def country_name(code):
    return dict(COUNTRIES).get(code, code)
    
def group_title(name):
    from ckan import model
    group = model.Group.by_name(name) 
    if group is not None:
        name = group.title
    return name

def file_type_title(code):
    return dict(FILE_TYPES).get(code, code)

def publisher_type_title(code):
    return dict(PUBLISHER_SOURCE_TYPES).get(code, code)

def organization_type_title(code):
    return dict(ORGANIZATION_TYPES).get(code, code)

def issue_title(code):
    return code.replace('-', ' ').title()

def get_organization_type(group_id):
    group = model.Group.get(group_id)
    if group:
        org_type = group.extras.get('publisher_organization_type')
        if org_type:
            return organization_type_title(org_type)
    return ''

def am_authorized_with_publisher(c, action, domain_object=None):
    from ckan import model
    from ckan.authz import Authorizer
    if not h.am_authorized(c, action, domain_object=domain_object):
        return False
    q = Authorizer.authorized_query(c.user, model.Group,
                                    action=model.Action.EDIT)
    if q.count() < 1:
        return False
    return True

def my_group():
    user = model.User.by_name(c.user)
    authzgroups = user and user.authorization_groups
    authzgroup = authzgroups and authzgroups[0]
    if authzgroup:
        group_id = re.match(r"group-(.*)-authz", authzgroup.name).group(1)
        group = model.Session.query(model.Group).filter_by(id=group_id).first()
        return group

def my_group_license():
    group = my_group()
    return group and group.extras.get('license_id', '')

def format_file_size(size):
    if size is None:
        return None
    try:
        size = float(size)
    except ValueError,e:
        return None

    for label in ['bytes','KB','MB','GB','TB']:
        if size < 1024.0:
            return "%3.1f%s" % (size, label)
        size /= 1024.0

h.am_authorized_with_publisher = am_authorized_with_publisher
h.country_name = country_name
h.group_title = group_title
h.file_type_title = file_type_title
h.organization_type_title = organization_type_title
h.publisher_type_title = publisher_type_title
h.issue_title = issue_title
h.publisher_record_fields = fields
h.my_group = my_group
h.my_group_license = my_group_license
h.format_file_size = format_file_size
h.get_organization_type = get_organization_type
