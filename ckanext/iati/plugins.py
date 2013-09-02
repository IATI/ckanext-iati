
# Bad imports: this should be in the toolkit
from ckan.lib.plugins import DefaultGroupForm
from ckanext.iati.logic.validators import db_date
from ckanext.iati.logic.converters import checkbox_value, strip

import ckan.plugins as p

class IatiPublishers(p.SingletonPlugin, DefaultGroupForm):

   # p.implements(p.IRoutes)
    p.implements(p.IGroupForm, inherit=True)
    p.implements(p.IConfigurer)

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
        schema.update({
            'state': [_ignore_not_sysadmin],
            'type': [_not_empty, _convert_to_extras],
            # TODO sort licensing
            #'license_id': [_convert_to_extras],
            'publisher_iati_id': [_ignore_missing, _convert_to_extras, unicode],
            'publisher_country': [_ignore_missing, _convert_to_extras, unicode],
            'publisher_segmentation': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_ui': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_frequency': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_thresholds': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_units': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_contact': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_agencies': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_field_exclusions': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_description': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_record_exclusions': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_timeliness': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_refs': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_constraints': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_data_quality': [ _ignore_missing, _convert_to_extras, unicode],
            'publisher_organization_type': [ _ignore_missing, _convert_to_extras, unicode],
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
            'filetype': [_convert_to_extras],
            'country': [_convert_to_extras, _ignore_missing],
            'data_updated': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_period-from': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_period-to': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_count': [_int_validator, _convert_to_extras, _ignore_missing],
            'archive_file': [checkbox_value, _convert_to_extras, _ignore_missing],
            'verified': [checkbox_value, _convert_to_extras, _ignore_missing],
            'language': [_convert_to_extras, _ignore_missing],
            'secondary_publisher': [strip, _convert_to_extras, _ignore_missing],
            'issue_type': [_convert_to_extras, _ignore_missing],
            'issue_message': [_convert_to_extras, _ignore_missing],
            'issue_date': [_convert_to_extras, _ignore_missing],
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
            'filetype': [_convert_to_extras],
            'country': [_convert_to_extras, _ignore_missing],
            'data_updated': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_period-from': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_period-to': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_count': [_int_validator, _convert_to_extras, _ignore_missing],
            'archive_file': [checkbox_value, _convert_to_extras, _ignore_missing],
            'verified': [checkbox_value, _convert_to_extras, _ignore_missing],
            'language': [_convert_to_extras, _ignore_missing],
            'secondary_publisher': [strip, _convert_to_extras, _ignore_missing],
            'issue_type': [_convert_to_extras, _ignore_missing],
            'issue_message': [_convert_to_extras, _ignore_missing],
            'issue_date': [_convert_to_extras, _ignore_missing],
        })

        return schema

    ## IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')

    ## ITemplateHelpers
    def get_helpers(self):
        import ckanext.iati.helpers as iati_helpers

        return {
            'get_countries': iati_helpers.get_countries
        }

