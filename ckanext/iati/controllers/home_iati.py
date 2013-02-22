from ckan import model
from ckan import logic
from ckan.lib.base import c, g, render
from ckan.controllers.home import HomeController
from ckan.lib.search import SearchError

class HomeIatiController(HomeController):

    def index(self):
        try:
            # package search
            context = {'model': model, 'session': model.Session,
                       'user': c.user or c.author}
            data_dict = {
                'q':'*:*',
                'facet.field':g.facets,
                'rows':0,
                'start':0,
            }
            query = logic.get_action('package_search')(context,data_dict)
            c.facets = query['facets']
            c.num_publishers = 0
            if c.facets and 'groups' in c.facets:
                c.num_publishers = len(c.facets['groups'].keys())

        except SearchError, se:
            c.num_publishers = 0
        return render('home/index.html')
