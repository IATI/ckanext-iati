from ckan.lib.base import *
from ckan.plugins import implements, SingletonPlugin, IRoutesExtension

class IatiRoutesExtension(SingletonPlugin):
    implements(IRoutesExtension, inherit=True)
    
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