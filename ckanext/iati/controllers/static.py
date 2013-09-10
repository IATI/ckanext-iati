from ckan.lib.base import render, BaseController

class StaticController(BaseController):

    def using_iati_data(self):
        return render('static/using-iati-data.html')

    def about(self):
        return render('static/about-2.html')

    def api(self):
        return render('static/registry-api.html')

    def help(self):
        return render('static/help.html')
