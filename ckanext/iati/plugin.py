import os

from logging import getLogger

from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IRoutes
from ckan.plugins import IConfigurer

import ckanext.iati

log = getLogger(__name__)

def configure_template_directory(config, relative_path):
    configure_served_directory(config, relative_path, 'extra_template_paths')

def configure_public_directory(config, relative_path):
    configure_served_directory(config, relative_path, 'extra_public_paths')

def configure_served_directory(config, relative_path, config_var):
    'Configure serving of public/template directories.'
    assert config_var in ('extra_template_paths', 'extra_public_paths')
    this_dir = os.path.dirname(ckanext.iati.__file__)
    absolute_path = os.path.join(this_dir, relative_path)
    if absolute_path not in config.get(config_var, ''):
        if config.get(config_var):
            config[config_var] += ',' + absolute_path
        else:
            config[config_var] = absolute_path

class IatiForms(SingletonPlugin):

    implements(IRoutes)
    implements(IConfigurer)

    def before_map(self, map):
        package_controller = 'ckanext.iati.controllers.package_iati:PackageIatiController'
        group_controller = 'ckanext.iati.controllers.group_iati:GroupIatiController'

        map.redirect('/package/new','/dataset/new')
        map.redirect('/package/edit/{id}','/dataset/edit/{id}')
        map.connect('/dataset/new', controller=package_controller, action='new')
        map.connect('/dataset/edit/{id}', controller=package_controller, action='edit')

        return map

    def after_map(self, map):
        return map

    def update_config(self, config):
        configure_template_directory(config, 'templates')

