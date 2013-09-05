from ckan.lib.base import render, BaseController

class StaticController(BaseController):

    def static_page(self, page):
        return render('static{0}.html'.format(page))
