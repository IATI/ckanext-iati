import inspect
import os

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