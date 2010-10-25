from ckan.lib.base import *

class IatiController(BaseController):

    def index(self):
        return render('iati.html', cache_expire=84600)
        

class HelpController(BaseController):

    def index(self):
        return render('help.html', cache_expire=84600)