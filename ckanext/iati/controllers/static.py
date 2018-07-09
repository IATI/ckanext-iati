from ckan.lib.base import redirect, render, BaseController

# TODO: replace with ckanext-pages


class StaticController(BaseController):

    def using_iati_data(self):
        return redirect('http://iatistandard.org/en/using-data/')

    def about(self):
        return redirect('http://iatistandard.org/en/using-data/IATI-tools-and-resources/using-IATI-registry/')

    def api(self):
        return redirect('http://iatistandard.org/en/using-data/IATI-tools-and-resources/using-IATI-registry/')

    def help(self):
        return redirect('http://iatistandard.org/en/guidance/preparing-organisation/organisation-account/how-to-register-with-iati/')

    def help_csv(self):
        return render('static/help_csv-import.html')

    def help_delete(self):
        return render('static/help_delete.html')

    def dashboard(self):
        return redirect('http://iatistandard.org/en/guidance/publishing-data/data-quality-/how-to-improve-you-data-quality-with-the-iati-dashboard/')
