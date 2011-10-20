import os

from logging import getLogger

from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IRoutes
from ckan.plugins import IConfigurer
from ckan.plugins import IActions

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

        map.connect('/group/new', controller=group_controller, action='new')
        map.connect('/group/edit/{id}', controller=group_controller, action='edit')

        csv_controller = 'ckanext.iati.controllers.spreadsheet:CSVController'
        map.connect('/csv/download', controller=csv_controller, action='download')
        map.connect('/csv/download/{publisher}', controller=csv_controller, action='download')
        map.connect('/csv/upload', controller=csv_controller, action='upload',
                    conditions=dict(method=['GET']))
        map.connect('/csv/upload', controller=csv_controller, action='upload',
                    conditions=dict(method=['POST']))

        return map

    def after_map(self, map):
        return map

    def update_config(self, config):
        configure_template_directory(config, 'templates')
        configure_public_directory(config, 'public')

class IatiActions(SingletonPlugin):

    implements(IActions)

    def get_actions(self):
        from ckanext.iati.logic.action.get import (package_show as package_show_iati,
                                                   package_show_rest as package_show_rest_iati)

        return {
            'package_show':package_show_iati,
            'package_show_rest':package_show_rest_iati
        }

