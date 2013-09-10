import logging

# Bad imports: this should be in the toolkit

from routes.mapper import SubMapper     # Maybe not this one
from ckan.lib.plugins import DefaultGroupForm
from ckanext.iati.logic.validators import db_date, iati_publisher_state_validator, iati_owner_org_validator
from ckanext.iati.logic.converters import checkbox_value, strip

import ckan.plugins as p

log = logging.getLogger(__name__)

class IatiPublishers(p.SingletonPlugin, DefaultGroupForm):

    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IGroupForm, inherit=True)
    p.implements(p.IConfigurer)

    ## IRoutes

    def before_map(self, map):

        map.redirect('/group/{url:.*}', '/publisher/{url}',
                     _redirect_code='301 Moved Permanently')
        map.redirect('/group', '/publisher',
                     _redirect_code='301 Moved Permanently')
        map.redirect('/organization/{url:.*}', '/publisher/{url}',
                     _redirect_code='301 Moved Permanently')
        map.redirect('/organization', '/publisher',
                     _redirect_code='301 Moved Permanently')

        map.redirect('/publishers', '/publisher')
        map.redirect('/publishers/{url:.*}', '/publisher/{url}')

        org_controller = 'ckan.controllers.organization:OrganizationController'
        with SubMapper(map, controller=org_controller) as m:
            m.connect('publishers_index', '/publisher', action='index')
            m.connect('/publisher/list', action='list')
            m.connect('/publisher/new', action='new')
            m.connect('/publisher/{action}/{id}',
                      requirements=dict(action='|'.join([
                          'delete',
                          'admins',
                          'member_new',
                          'member_delete',
                          'history'
                      ])))
            m.connect('publisher_activity', '/publisher/activity/{id}',
                      action='activity', ckan_icon='time')
            m.connect('publisher_read', '/publisher/{id}', action='read')
            m.connect('publisher_about', '/publisher/about/{id}',
                      action='about', ckan_icon='info-sign')
            m.connect('publisher_read', '/publisher/{id}', action='read',
                      ckan_icon='sitemap')
            m.connect('publisher_edit', '/publisher/edit/{id}',
                      action='edit', ckan_icon='edit')
            m.connect('publisher_members', '/publisher/edit_members/{id}',
                      action='members', ckan_icon='group')
            m.connect('publisher_bulk_process',
                      '/publisher/bulk_process/{id}',
                      action='bulk_process', ckan_icon='sitemap')

        map.redirect('/api/{ver:1|2|3}/rest/publisher',
                     '/api/{ver}/rest/group')
        map.redirect('/api/rest/publisher', '/api/rest/group')
        map.redirect('/api/{ver:1|2|3}/rest/publisher/{url:.*}',
                     '/api/{ver}/rest/group/{url:.*}')
        map.redirect('/api/rest/publisher/{url:.*}',
                     '/api/rest/group/{url:.*}')

        map.connect('publisher_members_read', '/publisher/members/{id}',
            controller='ckanext.iati.controllers.publisher:PublisherController',
            action='members_read', ckan_icon='group')

        return map

    ## IGroupForm

    def is_fallback(self):
        return True

    def group_types(self):
        return ['organization']

    def form_to_db_schema_options(self, options):
        ''' This allows us to select different schemas for different
        purpose eg via the web interface or via the api or creation vs
        updating. It is optional and if not available form_to_db_schema
        should be used.
        If a context is provided, and it contains a schema, it will be
        returned.
        '''
        schema = options.get('context', {}).get('schema', None)
        if schema:
            return schema

        if options.get('api'):
            if options.get('type') == 'create':
                return self.form_to_db_schema_api_create()
            else:
                return self.form_to_db_schema_api_update()
        else:
            return self.form_to_db_schema()

    def form_to_db_schema_api_create(self):
        schema = super(IatiPublishers, self).form_to_db_schema_api_create()
        schema = self._modify_group_schema(schema)
        return schema

    def form_to_db_schema_api_update(self):
        schema = super(IatiPublishers, self).form_to_db_schema_api_update()
        schema = self._modify_group_schema(schema)
        return schema

    def form_to_db_schema(self):
        schema = super(IatiPublishers, self).form_to_db_schema()
        schema = self._modify_group_schema(schema)
        return schema

    def _modify_group_schema(self, schema):

        # Import core converters and validators
        _convert_to_extras = p.toolkit.get_converter('convert_to_extras')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')

        default_validators = [_ignore_missing, _convert_to_extras, unicode]
        schema.update({
            'state': [iati_publisher_state_validator],
            'license_id': [_convert_to_extras],
            'publisher_source_type': default_validators,
            'publisher_iati_id': default_validators,
            'publisher_country': default_validators,
            'publisher_segmentation': default_validators,
            'publisher_ui': default_validators,
            'publisher_frequency': default_validators,
            'publisher_thresholds': default_validators,
            'publisher_units': default_validators,
            'publisher_contact': default_validators,
            'publisher_agencies': default_validators,
            'publisher_field_exclusions': default_validators,
            'publisher_description': default_validators,
            'publisher_record_exclusions': default_validators,
            'publisher_timeliness': default_validators,
            'publisher_refs': default_validators,
            'publisher_constraints': default_validators,
            'publisher_data_quality': default_validators,
            'publisher_organization_type': default_validators,
        })

        return schema

    def db_to_form_schema(self):

        # Import core converters and validators
        _convert_from_extras = p.toolkit.get_converter('convert_from_extras')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')
        _ignore = p.toolkit.get_validator('ignore')
        _not_empty = p.toolkit.get_validator('not_empty')

        schema = super(IatiPublishers, self).form_to_db_schema()

        default_validators = [_convert_from_extras, _ignore_missing]
        schema.update({
            'state': [],
            'license_id': default_validators,
            'publisher_source_type': default_validators,
            'publisher_country': default_validators,
            'publisher_iati_id': default_validators,
            'publisher_segmentation': default_validators,
            'publisher_ui': default_validators,
            'publisher_frequency': default_validators,
            'publisher_thresholds': default_validators,
            'publisher_units': default_validators,
            'publisher_contact': default_validators,
            'publisher_agencies': default_validators,
            'publisher_field_exclusions': default_validators,
            'publisher_description': default_validators,
            'publisher_record_exclusions': default_validators,
            'publisher_timeliness': default_validators,
            'publisher_refs': default_validators,
            'publisher_constraints': default_validators,
            'publisher_data_quality': default_validators,
            'publisher_organization_type': default_validators,
            'groups': [_ignore],
            'tags': [_ignore],
            'approval_status': [_ignore],
            #TODO: this should be handled in core
            'num_followers': [_not_empty],
            'package_count': [_not_empty],
        })

        return schema

    # IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')


class IatiDatasets(p.SingletonPlugin, p.toolkit.DefaultDatasetForm):

    p.implements(p.IDatasetForm, inherit=True)
    p.implements(p.IPackageController, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)

    ## IDatasetForm

    def is_fallback(self):
        return True

    def package_types(self):
        return []

    def _modify_package_schema(self, schema):

        # Import core converters and validators
        _convert_to_extras = p.toolkit.get_converter('convert_to_extras')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')
        _ignore_empty = p.toolkit.get_validator('ignore_empty')
        _int_validator = p.toolkit.get_validator('int_validator')

        schema.update({
            'filetype': [_ignore_missing, _convert_to_extras],
            'country': [_ignore_missing, _convert_to_extras],
            'data_updated': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_period-from': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_period-to': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_count': [_ignore_missing, _int_validator, _convert_to_extras],
            'archive_file': [_ignore_missing, checkbox_value, _convert_to_extras],
            'verified': [_ignore_missing, checkbox_value, _convert_to_extras],
            'language': [_ignore_missing, _convert_to_extras],
            'secondary_publisher': [_ignore_missing, strip, _convert_to_extras],
            'issue_type': [_ignore_missing, _convert_to_extras],
            'issue_message': [_ignore_missing, _convert_to_extras],
            'issue_date': [_ignore_missing, _convert_to_extras],
        })

        schema['owner_org'].append(iati_owner_org_validator)


        return schema

    def create_package_schema(self):
        schema = super(IatiDatasets, self).create_package_schema()
        schema = self._modify_package_schema(schema)
        return schema

    def update_package_schema(self):
        schema = super(IatiDatasets, self).update_package_schema()
        schema = self._modify_package_schema(schema)
        return schema

    def show_package_schema(self):
        schema = super(IatiDatasets, self).show_package_schema()

        # Import core converters and validators
        _convert_from_extras = p.toolkit.get_converter('convert_from_extras')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')
        _ignore_empty = p.toolkit.get_validator('ignore_empty')
        _int_validator = p.toolkit.get_validator('int_validator')

        schema.update({
            'filetype': [_ignore_missing, _convert_from_extras],
            'country': [_ignore_missing, _convert_from_extras],
            'data_updated': [_ignore_missing, _ignore_empty, db_date, _convert_from_extras],
            'activity_period-from': [_ignore_missing, _ignore_empty, db_date, _convert_from_extras],
            'activity_period-to': [_ignore_missing, _ignore_empty, db_date, _convert_from_extras],
            'activity_count': [_ignore_missing, _int_validator, _convert_from_extras],
            'archive_file': [_ignore_missing, checkbox_value, _convert_from_extras],
            'verified': [_ignore_missing, checkbox_value, _convert_from_extras],
            'language': [_ignore_missing, _convert_from_extras],
            'secondary_publisher': [_ignore_missing, strip, _convert_from_extras],
            'issue_type': [_ignore_missing, _convert_from_extras],
            'issue_message': [_ignore_missing, _convert_from_extras],
            'issue_date': [_ignore_missing, _convert_from_extras],
        })

        return schema

    ## IPackageController
    def after_show(self, context, data_dict):
        if data_dict.get('owner_org'):
            org = p.toolkit.get_action('organization_show')({}, {'id': data_dict['owner_org']})
            if org:
                new_extras = []
                for key in ('publisher_source_type', 'publisher_organization_type', 'publisher_country',
                            'publisher_iati_id',):
                    new_extras.append({'key': key, 'value': org.get(key, '')})

                data_dict['extras'].extend(new_extras)

        return data_dict

    ## IConfigurer
    def update_config(self, config):
        if not config.get('ckan.site_url'):
            raise Exception('This extension requires site_url to be set up in the ini file')

        p.toolkit.add_template_directory(config, 'theme/templates')

    ## ITemplateHelpers
    def get_helpers(self):
        import ckanext.iati.helpers as iati_helpers

        function_names = (
            'get_countries',
            'get_publisher_source_types',
            'get_licenses',
            'get_organization_types',
            'is_route_active'
        )
        return _get_module_functions(iati_helpers, function_names)

    ## IActions
    def get_actions(self):
        import ckanext.iati.logic.action as iati_actions

        function_names = (
            'package_create',
            'package_update',
            'organization_create',
            'organization_update',
            'issues_report_csv',
        )
        return _get_module_functions(iati_actions, function_names)

    ## IAuthFunctions
    def get_auth_functions(self):
        from ckanext.iati.logic import auth as iati_auth

        function_names = (
            'issues_report_csv',
        )
        return _get_module_functions(iati_auth, function_names)

def _get_module_functions(module, function_names):
    functions = {}
    for f in function_names:
        functions[f] = module.__dict__[f]

    return functions


class IatiTheme(p.SingletonPlugin):

    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.IFacets, inherit=True)

    # IRoutes
    def before_map(self, map):
        static_controller = 'ckanext.iati.controllers.static:StaticController'

        with SubMapper(map, controller=static_controller) as m:
            m.connect('using-iati-data', '/using-iati-data',
                action='using_iati_data')
            m.connect('about-2', '/about-2', action='about')
            m.connect('api', '/registry-api', action='api')
            m.connect('help', '/help', action='help')

        return map

    # IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')
        p.toolkit.add_public_directory(config, 'theme/public')
        p.toolkit.add_resource('theme/fanstatic_library', 'ckanext-iati')

    # IFacets
    def dataset_facets(self, facets_dict, package_type):
        ''' Update the facets_dict and return it. '''
        facets_dict.clear()
        facets_dict.update({
            'groups': p.toolkit._('Publisher'),
            'secondary_publisher': p.toolkit._('Secondary Publisher'),
            'publisher_source_type': p.toolkit._('Source'),
            'publisher_organization_type': p.toolkit._('Organization Type'),
            'country': p.toolkit._('Country'),
            'filetype': p.toolkit._('File Type'),
            'issue_type': p.toolkit._('Issues'),
		})
        return facets_dict

class IatiCsvImporter(p.SingletonPlugin):

    p.implements(p.IConfigurer)
    p.implements(p.IRoutes)

    # IRoutes
    def before_map(self, map):
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

    # IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')
        p.toolkit.add_public_directory(config, 'theme/public')
        p.toolkit.add_resource('theme/fanstatic_library', 'ckanext-iati')
