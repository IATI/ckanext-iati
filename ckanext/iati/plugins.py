
# Bad imports: this should be in the toolkit

from routes.mapper import SubMapper     # Maybe not this one
from ckan.lib.plugins import DefaultGroupForm
from ckanext.iati.logic.validators import db_date
from ckanext.iati.logic.converters import checkbox_value, strip

import ckan.plugins as p


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
            m.connect('publisher_members', '/publisher/members/{id}',
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

        return map

    ## IGroupForm

    def is_fallback(self):
        return True

    def group_types(self):
        return ['organization']

    def form_to_db_schema(self):

        # Import core converters and validators
        _convert_to_extras = p.toolkit.get_converter('convert_to_extras')
        _ignore_not_sysadmin = p.toolkit.get_validator('ignore_not_sysadmin')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')
        _not_empty = p.toolkit.get_validator('not_empty')

        schema = super(IatiPublishers, self).form_to_db_schema()
        default_validators = [_ignore_missing, _convert_to_extras, unicode]
        schema.update({
            'state': [_ignore_not_sysadmin],
            'type': [_not_empty, _convert_to_extras],
            # TODO sort licensing
            #'license_id': [_convert_to_extras],
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
        _ignore_not_sysadmin = p.toolkit.get_validator('ignore_not_sysadmin')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')
        _not_empty = p.toolkit.get_validator('not_empty')

        schema = super(IatiPublishers, self).form_to_db_schema()
        schema.update({
            'state': [_ignore_not_sysadmin],
            'type': [_convert_from_extras],
            'license_id': [_convert_from_extras],
            'publisher_country': [_convert_from_extras],
            'publisher_iati_id': [_convert_from_extras, _ignore_missing],
            'publisher_segmentation': [_convert_from_extras],
            'publisher_ui': [_convert_from_extras],
            'publisher_frequency': [_convert_from_extras],
            'publisher_thresholds': [_convert_from_extras],
            'publisher_units': [_convert_from_extras],
            'publisher_contact': [_convert_from_extras],
            'publisher_agencies': [_convert_from_extras],
            'publisher_field_exclusions': [_convert_from_extras],
            'publisher_description': [_convert_from_extras],
            'publisher_record_exclusions': [_convert_from_extras],
            'publisher_timeliness': [_convert_from_extras],
            'publisher_refs': [_convert_from_extras],
            'publisher_constraints': [_convert_from_extras],
            'publisher_data_quality': [_convert_from_extras],
            'publisher_organization_type': [_convert_from_extras],
            #TODO: this should be handled in core
            'num_followers': [_not_empty],
            'package_count': [_not_empty],
        })

        return schema

    ## IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')


class IatiDatasets(p.SingletonPlugin, p.toolkit.DefaultDatasetForm):

    p.implements(p.IDatasetForm, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.ITemplateHelpers)

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

        return schema

    ## IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')

    ## ITemplateHelpers
    def get_helpers(self):
        import ckanext.iati.helpers as iati_helpers

        function_names = (
            'get_countries',
            'get_publisher_source_types',
            'get_licenses',
            'get_organization_types',
        )

        helpers = {}
        for f in function_names:
            helpers[f] = iati_helpers.__dict__[f]

        return helpers
