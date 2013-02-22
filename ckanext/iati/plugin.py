import os

from logging import getLogger

from ckan.model import Package, Group
from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IRoutes
from ckan.plugins import IConfigurer
from ckan.plugins import IActions
from ckan.plugins import IGroupController
from ckan.plugins import IPackageController

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
        home_controller = 'ckanext.iati.controllers.home_iati:HomeIatiController'
        package_controller = 'ckanext.iati.controllers.package_iati:PackageIatiController'
        group_controller = 'ckanext.iati.controllers.group_iati:GroupIatiController'

        map.connect('/', controller=home_controller, action='index')

        map.redirect('/package/new','/dataset/new')
        map.redirect('/package/edit/{id}','/dataset/edit/{id}')
        map.connect('/dataset/new', controller=package_controller, action='new')
        map.connect('/dataset/edit/{id}', controller=package_controller, action='edit')

        map.redirect('/group/{url:.*}', '/publisher/{url}', _redirect_code='301 Moved Permanently')
        map.redirect('/group', '/publisher', _redirect_code='301 Moved Permanently')
        map.redirect('/publishers', '/publisher')
        map.redirect('/publishers/{url:.*}', '/publisher/{url}')
        map.connect('/publisher', controller=group_controller, action='index')
        map.connect('/publisher/list', controller=group_controller, action='list')
        map.connect('/publisher/new', controller=group_controller, action='new')
        map.connect('/publisher/{action}/{id}', controller=group_controller,
            requirements=dict(action='|'.join([
            'edit',
            'authz',
            'history'
            ]))
            )
        map.connect('/publisher/{id}', controller=group_controller, action='read')

        map.redirect('/api/{ver:1|2|3}/rest/publisher', '/api/{ver}/rest/group')
        map.redirect('/api/rest/publisher', '/api/rest/group')
        map.redirect('/api/{ver:1|2|3}/rest/publisher/{url:.*}', '/api/{ver}/rest/group/{url:.*}')
        map.redirect('/api/rest/publisher/{url:.*}', '/api/rest/group/{url:.*}')

        csv_controller = 'ckanext.iati.controllers.spreadsheet:CSVController'
        map.connect('/csv/download', controller=csv_controller, action='download')
        map.connect('/csv/download/{publisher}', controller=csv_controller, action='download')
        map.connect('/csv/upload', controller=csv_controller, action='upload',
                    conditions=dict(method=['GET']))
        map.connect('/csv/upload', controller=csv_controller, action='upload',
                    conditions=dict(method=['POST']))


        # Redirects needed after updating the datasets name for some of the publishers
        map.redirect('/dataset/wb-{code}','/dataset/worldbank-{code}',_redirect_code='301 Moved Permanently')
        map.redirect('/dataset/minbuza_activities','/dataset/minbuza_nl-activities',_redirect_code='301 Moved Permanently')
        map.redirect('/dataset/minbuza_organisation','/dataset/minbuza_nl-organisation',_redirect_code='301 Moved Permanently')

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

class IatiLicenseOverride(SingletonPlugin):

    implements(IGroupController,inherit=True)
    implements(IPackageController,inherit=True)

    def _override_license(self,group):
        group_license_id = group.extras.get('license_id')

        if group.packages and group_license_id:
            # Check if license changed
            if group.packages[0].license_id != group_license_id:
                for package in group.packages:
                    package.license_id = group_license_id

    def create(self,entity):
        if isinstance(entity,Package):
            # Assign group's license to the newly created package
            group = entity.groups[0] if len(entity.groups) else None
            if group and group.extras.get('license_id'):
                entity.license_id = group.extras.get('license_id')

        elif isinstance(entity,Group):
            self._override_license(entity)

    def edit(self,entity):
        if isinstance(entity,Package):
            # Licenses are only handled at the group level
            pass
        elif isinstance(entity,Group):
            self._override_license(entity)

class IatiFeeds(SingletonPlugin):

    implements(IRoutes)

    def before_map(self, map):
        feed_controller = 'ckanext.iati.controllers.feed:FeedController'

        map.connect('/feed/registry.{format:atom}', controller=feed_controller, action='general')
        map.connect('/feed/country/{id}.{format:atom}', controller=feed_controller, action='country')
        map.connect('/feed/publisher/{id}.{format:atom}', controller=feed_controller, action='publisher')
        map.connect('/feed/organisation_type/{id}.{format:atom}', controller=feed_controller, action='organisation_type')
        map.connect('/feed/custom.{format:atom}', controller=feed_controller, action='custom')

        return map

    def after_map(self, map):
        return map

