import inspect
import os

import patch
import authz
import preview

from controllers import * 

class IatiPlugin(object):
    def __init__(self, config): pass
    
    def make_map_end(self, map):
        
        #import ckanext.deliverance
        map.connect('/iati', controller='ckanext.iati:IatiController', 
                             action='index')
        map.connect('/help', controller='ckanext.iati:HelpController', 
                             action='index')
        return map