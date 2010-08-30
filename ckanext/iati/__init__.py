import inspect
import os
from forms.countries import COUNTRIES

def country_name(code):
    return dict(COUNTRIES).get(code, code)

import ckan.lib.helpers as h
h.country_name = country_name 

class TemplatingPlugin(object):
    
    def __init__(self, config):
        this_file = os.path.dirname(inspect.currentframe().f_code.co_filename)
        config['extra_template_paths'] = ', '.join((os.path.join(this_file, '../../templates'),
                                                   config.get('extra_template_paths', '')))
        config['extra_public_paths'] = ', '.join((os.path.join(this_file, '../../public'),
                                                  config.get('extra_public_paths', '')))
        #from pprint import pprint
        #pprint(config)
        self.config = config