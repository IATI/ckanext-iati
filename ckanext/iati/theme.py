import os

from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IConfigurer

class IatiThemeExtension(SingletonPlugin):
    implements(IConfigurer, inherit=True)

    def update_config(self, config):
        here = os.path.dirname(__file__)
        rootdir = os.path.dirname(os.path.dirname(here))
        our_public_dir = os.path.join(rootdir, 'ckanext', 'iati', '', 'public')
        template_dir = os.path.join(rootdir, 'ckanext', 'iati', 'templates')
        config['extra_public_paths'] = ','.join([our_public_dir,
                config.get('extra_public_paths', '')])
        config['extra_template_paths'] = ','.join([template_dir,
                config.get('extra_template_paths', '')])


