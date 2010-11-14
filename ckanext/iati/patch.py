from forms.countries import COUNTRIES
import ckan.lib.helpers as h

# TODO move this to helpers proper
def country_name(code):
    return dict(COUNTRIES).get(code, code)
    
def group_title(name):
    from ckan import model
    group = model.Group.by_name(name) 
    if group is not None:
        name = group.title
    return name
    
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
    

h.am_authorized_with_publisher = am_authorized_with_publisher
h.country_name = country_name
h.group_title = group_title