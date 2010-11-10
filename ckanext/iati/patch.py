from forms.countries import COUNTRIES

# TODO move this to helpers proper
def country_name(code):
    return dict(COUNTRIES).get(code, code)
    
def group_title(name):
    from ckan import model
    group = model.Group.by_name(name) 
    if group is not None:
        name = group.title
    return name
    
import ckan.lib.helpers as h
h.country_name = country_name
h.group_title = group_title