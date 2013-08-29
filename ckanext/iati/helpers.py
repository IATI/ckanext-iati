from ckanext.iati.lists import COUNTRIES

# TODO: Move the functions on patch.py and expose them via ITemplateHelpers,
# but only the ones that we need!

def get_countries():
    return COUNTRIES
