from ckan.lib.base import *
from ckan.plugins import implements, SingletonPlugin, IRoutes

class IatiRoutesExtension(SingletonPlugin):
    implements(IRoutes, inherit=True)
    
    def before_map(self, map):
        return map
    
    def after_map(self, map):
        map.connect('/iati', controller='ckanext.iati.controllers:IatiController', 
                             action='index')
        map.connect('/help', controller='ckanext.iati.controllers:HelpController', 
                             action='index')
        return map


class IatiController(BaseController):

    def index(self):
        return render('iati.html', cache_expire=84600)
        

class HelpController(BaseController):

    def index(self):
        return render('help.html', cache_expire=84600)
