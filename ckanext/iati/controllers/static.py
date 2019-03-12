from ckan.lib.base import render, BaseController

# TODO: replace with ckanext-pages


class StaticController(BaseController):

    def help_csv(self):
        return render('static/help_csv-import.html')

    def help_delete(self):
        return render('static/help_delete.html')

