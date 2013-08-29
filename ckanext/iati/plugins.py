
# Bad imports: this should be in the toolkit
from ckan.lib.plugins import DefaultGroupForm


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
        p.toolkit.add_template_directory(config, 'templates_new')

