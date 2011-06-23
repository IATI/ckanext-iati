import os

from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IConfigurer,IRoutes

class IatiThemeExtension(SingletonPlugin):
    implements(IConfigurer, inherit=True)
    implements(IRoutes, inherit=True)
    def before_map(self, map):
        map.connect('/package/new', controller='package_formalchemy', action='new')
        map.connect('/package/edit/{id}', controller='package_formalchemy', action='edit')
        map.connect('/group/new', controller='group_formalchemy', action='new')
        map.connect('/group/edit/{id}', controller='group_formalchemy', action='edit')

        return map

    def update_config(self, config):
        here = os.path.dirname(__file__)
        rootdir = os.path.dirname(os.path.dirname(here))
        our_public_dir = os.path.join(rootdir, 'ckanext', 'iati', '', 'public')
        template_dir = os.path.join(rootdir, 'ckanext', 'iati', 'templates')
        config['extra_public_paths'] = ','.join([our_public_dir,
                config.get('extra_public_paths', '')])
        config['extra_template_paths'] = ','.join([template_dir,
                config.get('extra_template_paths', '')])


