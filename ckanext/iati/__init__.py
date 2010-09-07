import inspect
import os
from forms.countries import COUNTRIES


# TODO move this to helpers proper
def country_name(code):
    return dict(COUNTRIES).get(code, code)
import ckan.lib.helpers as h
h.country_name = country_name 

from ckan.model import Package, Group
import ckan.model.authz
from ckan.model.authz import setup_user_roles, Role, Action
def setup_default_user_roles(domain_object, admins=[]):
    # sets up roles for visitor, logged-in user and any admins provided
    # admins is a list of User objects
    assert isinstance(domain_object, (Package, Group))
    assert isinstance(admins, list)
    if type(domain_object) == Package:
        visitor_roles = [Role.READER]
        logged_in_roles = [Role.READER]
    elif type(domain_object) == Group:
        visitor_roles = [Role.READER]
        logged_in_roles = [Role.READER]
    setup_user_roles(domain_object, visitor_roles, logged_in_roles, admins)

ckan.model.authz.setup_default_user_roles = setup_default_user_roles

ckan.model.authz.default_role_actions = [
    (Role.EDITOR, Action.EDIT),
    (Role.EDITOR, Action.CREATE),
    (Role.EDITOR, Action.READ),  
    (Role.READER, Action.READ),
    ]

class TemplatingPlugin(object):
    
    def __init__(self, config):
        this_file = os.path.dirname(__file__)
        config['extra_template_paths'] = ', '.join((os.path.join(this_file, '../../templates'),
                                                   config.get('extra_template_paths', '')))
        config['extra_public_paths'] = ', '.join((os.path.join(this_file, '../../public'),
                                                  config.get('extra_public_paths', '')))
        #from pprint import pprint
        #pprint(config)
        self.config = config