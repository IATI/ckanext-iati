from forms.countries import COUNTRIES

# TODO move this to helpers proper
def country_name(code):
    return dict(COUNTRIES).get(code, code)
import ckan.lib.helpers as h
h.country_name = country_name