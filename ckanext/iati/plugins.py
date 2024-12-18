import logging
import requests
from ckan.common import c
# Bad imports: this should be in the toolkit
import json
import os
from routes.mapper import SubMapper     # Maybe not this one
from ckan.lib.plugins import DefaultOrganizationForm
from ckanext.iati.views.archiver import ArchiverViewRun
import ckan.plugins as p
from ckan.common import config
from ckan.lib.navl.validators import unicode_safe
from ckanext.iati.logic.validators import (
    db_date,
    iati_publisher_state_validator,
    iati_owner_org_validator,
    iati_dataset_name,
    iati_resource_count,
    valid_url,
    iati_one_resource,
    email_validator,
    file_type_validator,
    iati_org_identifier_validator,
    remove_leading_or_trailing_spaces,
    licence_validator,
    country_code,
    change_publisher_id_or_org_id,
    first_publisher_date_validator,
    validate_new_publisher_id_against_old,
    not_missing,
    not_empty,
    iati_publisher_name_validator,
    iati_org_identifier_name_validator,
)
from ckanext.iati.logic.converters import strip, convert_date_string_to_iso_format
import ckanext.iati.helpers as iati_helpers
from ckanext.iati.model import IATIRedirects
from ckanext.iati.views.publisher import publisher_blueprint, publisher_with_user_blueprint
from ckanext.iati.views.reports import issues
from ckanext.iati.views.dashboard import custom_dashboard
from ckanext.iati.views.admin import admin_tabs
from ckanext.iati.views.helper_pages import helper_pages
from ckanext.iati.views.spreadsheet import spreadsheet
from ckanext.iati.views.archiver import archiver as archiver_blueprint
from ckanext.iati.views.registration import registration_blueprint
import ckanext.iati.emailer as emailer

log = logging.getLogger(__name__)

TIMEOUT = 5

class IatiPublishers(p.SingletonPlugin, DefaultOrganizationForm):

    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IGroupForm, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.IBlueprint)

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
        map.redirect('/dataset_search','/dataset')

        map.redirect('/api/{ver:1|2|3}/rest/publisher',
                     '/api/{ver}/rest/group')
        map.redirect('/api/rest/publisher', '/api/rest/group')
        map.redirect('/api/{ver:1|2|3}/rest/publisher/{url:.*}',
                     '/api/{ver}/rest/group/{url:.*}')
        map.redirect('/api/rest/publisher/{url:.*}',
                     '/api/rest/group/{url:.*}')

        # custom redirects
        redirects = {
            '/using-iati-data': 'http://iatistandard.org/en/using-data/',
            '/registry-dashboard': 'http://iatistandard.org/en/guidance/publishing-data/data-quality-/how-to-improve-you-data-quality-with-the-iati-dashboard/',
            '/about': 'http://iatistandard.org/en/using-data/IATI-tools-and-resources/using-IATI-registry/',
            '/registry-api': 'http://iatistandard.org/en/using-data/IATI-tools-and-resources/using-IATI-registry/',
            '/help': 'http://iatistandard.org/en/guidance/preparing-organisation/organisation-account/how-to-register-with-iati/'
        }

        for k, v in redirects.items():
            map.redirect(k, v)

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
        _not_empty = p.toolkit.get_validator('not_empty')

        _unicode_safe = p.toolkit.get_validator('unicode_safe')
        _group_name_validator = p.toolkit.get_validator('group_name_validator')

        default_validators = [_ignore_missing, _convert_to_extras, unicode_safe]
        schema.update({
            'state': [iati_publisher_state_validator],
            'title': [_not_empty, remove_leading_or_trailing_spaces],
            'name': [_not_empty, _unicode_safe, iati_publisher_name_validator, _group_name_validator,
                     change_publisher_id_or_org_id, validate_new_publisher_id_against_old],
            'license_id': [_convert_to_extras, licence_validator],
            'publisher_source_type': [_not_empty, _convert_to_extras, str],
            'publisher_iati_id': [_not_empty, remove_leading_or_trailing_spaces, iati_org_identifier_validator,
                                  _convert_to_extras, str, change_publisher_id_or_org_id,
                                  iati_org_identifier_name_validator],
            'publisher_country': default_validators,
            'publisher_segmentation': default_validators,
            'publisher_ui': default_validators,
            'publisher_ui_url': [_ignore_missing, valid_url, _convert_to_extras, str],
            'publisher_url': [_ignore_missing, valid_url, _convert_to_extras, str],
            'publisher_frequency_select': default_validators,
            'publisher_frequency': default_validators,
            'publisher_thresholds': default_validators,
            'publisher_units': default_validators,
            'publisher_contact': default_validators,
            'publisher_contact_email': [_not_empty, _convert_to_extras, email_validator, str],
            'publisher_agencies': default_validators,
            'publisher_field_exclusions': default_validators,
            'publisher_description': default_validators,
            'publisher_record_exclusions': default_validators,
            'publisher_timeliness': default_validators,
            'publisher_refs': default_validators,
            'publisher_constraints': default_validators,
            'publisher_data_quality': default_validators,
            'publisher_organization_type': [_not_empty, _convert_to_extras, str],
            'publisher_implementation_schedule': default_validators,
            'publisher_first_publish_date': [_ignore_missing, convert_date_string_to_iso_format, _convert_to_extras,
                                             str, first_publisher_date_validator]

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
            'publisher_ui_url': default_validators,
            'publisher_url': default_validators,
            'publisher_frequency_select': default_validators,
            'publisher_frequency': default_validators,
            'publisher_thresholds': default_validators,
            'publisher_units': default_validators,
            'publisher_contact': default_validators,
            'publisher_contact_email': default_validators,
            'publisher_agencies': default_validators,
            'publisher_field_exclusions': default_validators,
            'publisher_description': default_validators,
            'publisher_record_exclusions': default_validators,
            'publisher_timeliness': default_validators,
            'publisher_refs': default_validators,
            'publisher_constraints': default_validators,
            'publisher_data_quality': default_validators,
            'publisher_organization_type': default_validators,
            'publisher_implementation_schedule': default_validators,
            'publisher_first_publish_date': default_validators,
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
        p.toolkit.add_public_directory(config, 'assets')

    # IBlueprint
    def get_blueprint(self):
        # blueprint for this extension
        return [
            publisher_blueprint,
            custom_dashboard, issues,
            admin_tabs, helper_pages,
            spreadsheet,
            archiver_blueprint,
            publisher_with_user_blueprint,
            registration_blueprint
        ]


class IatiDatasets(p.SingletonPlugin, p.toolkit.DefaultDatasetForm):

    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IDatasetForm, inherit=True)
    p.implements(p.IPackageController, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)
    p.implements(p.IValidators)

    ## IRoutes
    def before_map(self, map):

        # Redirects needed after updating the datasets name for some of the publishers
        map.redirect('/dataset/wb-{code}','/dataset/worldbank-{code}',_redirect_code='301 Moved Permanently')
        map.redirect('/dataset/minbuza_activities','/dataset/minbuza_nl-activities',_redirect_code='301 Moved Permanently')
        map.redirect('/dataset/minbuza_organisation','/dataset/minbuza_nl-organisation',_redirect_code='301 Moved Permanently')

        # Redirect the old extension feeds to the ones in core
        map.redirect('/feed/registry.atom', '/feeds/dataset.atom', _redirect_code='301 Moved Permanently')
        map.redirect('/feed/publisher/{id}.atom', '/feeds/group/{id}.atom', _redirect_code='301 Moved Permanently')
        map.redirect('/feed/custom.atom', '/feeds/custom.atom', _redirect_code='301 Moved Permanently')
        map.redirect('/feed/country/{id}.atom', '/feeds/custom.atom?extras_country={id}', _redirect_code='301 Moved Permanently')
        map.redirect('/feed/organisation_type/{id}.atom', '/feeds/custom.atom?extras_publisher_organization_type={id}', _redirect_code='301 Moved Permanently')

        # Custom redirects for dataset renames
        # Add a new line for each redirect, in the form
        #
        #   ('old_name', 'new_name',),
        #
        renames = [
            ('ciuk-org', 'ciuk-activity'),
            ('uncdf-org', 'uncdf-activity'),
            ('plan_uk-org210613', 'plan_uk-activity'),
            # ('manxtimes-org', 'manxtimes-activity'),
            ('international-alert-org', 'international-alert-activity'),
            ('globalintegrity-org', 'globalintegrity-activity'),
        ]

        for rename in renames:
            # Dataset pages
            map.redirect('/dataset/' + rename[0], '/dataset/' + rename[1],
                     _redirect_code='301 Moved Permanently')
            map.redirect('/dataset/{url:.*}/' + rename[0], '/dataset/{url}/' + rename[1],
                     _redirect_code='301 Moved Permanently')
        return map

    ## IDatasetForm
    def is_fallback(self):
        return True

    def package_types(self):
        return []

    def package_form(self):
        return 'package/new_package_form.html'

    def _modify_package_schema(self, schema):

        # Import core converters and validators
        _convert_to_extras = p.toolkit.get_converter('convert_to_extras')
        _ignore_missing = p.toolkit.get_validator('ignore_missing')
        _ignore_empty = p.toolkit.get_validator('ignore_empty')
        _int_validator = p.toolkit.get_validator('int_validator')
        _not_empty = p.toolkit.get_validator('not_empty')

        schema.update({
            'filetype': [_ignore_missing, file_type_validator, _convert_to_extras],
            'country': [_ignore_missing, _convert_to_extras, country_code],
            'data_updated': [_ignore_missing, _ignore_empty, db_date, _convert_to_extras],
            'activity_count': [_ignore_missing, _int_validator, _convert_to_extras],
            'iati_version': [_ignore_missing, _convert_to_extras],
            'language': [_ignore_missing, _convert_to_extras],
            'secondary_publisher': [_ignore_missing, strip, _convert_to_extras],
            'issue_type': [_ignore_missing, _convert_to_extras],
            'issue_message': [_ignore_missing, _convert_to_extras],
            'issue_date': [_ignore_missing, _convert_to_extras],
        })

        schema['name'].extend([iati_dataset_name, iati_one_resource])
        schema['owner_org'].append(iati_owner_org_validator)

        schema['resources']['url'].extend([_not_empty, iati_resource_count, strip, valid_url])

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
            'filetype': [_ignore_missing, file_type_validator, _convert_from_extras],
            'country': [_ignore_missing, _convert_from_extras],
            'data_updated': [_ignore_missing, _ignore_empty, db_date, _convert_from_extras],
            'activity_count': [_ignore_missing, _int_validator, _convert_from_extras],
            'iati_version': [_ignore_missing, _convert_from_extras],
            'language': [_ignore_missing, _convert_from_extras],
            'secondary_publisher': [_ignore_missing, strip, _convert_from_extras],
            'issue_type': [_ignore_missing, _convert_from_extras],
            'issue_message': [_ignore_missing, _convert_from_extras],
            'issue_date': [_ignore_missing, _convert_from_extras],
            # validation status only in show, as it's a read only field added from before_index
            'validation_status': [_ignore_missing, _convert_from_extras],
        })

        return schema

    def _get_license_register(self):
        if not hasattr(self, '_license_register'):
            import ckan.model.license as _license
            self._license_register = _license.LicenseRegister()
        return self._license_register

    ## IPackageController
    def after_show(self, context, data_dict):
        if data_dict.get('owner_org'):
            org = p.toolkit.get_action('organization_show')(context, {'id': data_dict['owner_org']})
            if org:
                # Inherit license from publisher
                license = self._get_license_register().get(org.get('license_id'))
                if license:
                    data_dict['license_id'] = license.id
                    if license.url:
                        data_dict['license_url'] = license.url
                    if license.title:
                        data_dict['license_title'] = license.title
                data_dict['publisher_source_type'] = org.get('publisher_source_type', '')
                data_dict['publisher_organization_type'] = org.get('publisher_organization_type', '')
                data_dict['publisher_iati_id'] = org.get('publisher_iati_id', '')
                data_dict['publisher_country'] = org.get('publisher_country', '')
        return data_dict

    def after_create(self, context, pkg_dict):
        """
        Call the archiver view after create
        :return: None
        """
        if not context.get('disable_archiver', False):
            log.info("Running archiver as background job as package create")
            log.info(pkg_dict.get('id', ''))
            ArchiverViewRun.run_archiver_after_package_create_update(pkg_dict.get("id", None))
        else:
            log.info('Ignoring archiver run since archiver is disabled in context')
        return pkg_dict

    def after_update(self, context, pkg_dict):
        """
        Call the archiver view run after update
        :return: None
        """
        if not context.get('disable_archiver', False):
            log.info("Running archiver as background job as package update")
            ArchiverViewRun.run_archiver_after_package_create_update(pkg_dict.get("id", None))
        else:
            log.info('Ignoring archiver run since archiver is disabled in context')

        return pkg_dict
    
    def before_search(self, data_dict):
        if not data_dict.get('sort', ''):
            data_dict['sort'] = 'title_string asc'

        if 'owner_org' in data_dict.get('q', ''):
            data_dict['fq'] += ' organization:"%s"' % c.group_dict.get('name')
            q = data_dict['q']
            import re
            o = ' owner_org:"%s"'%c.group_dict.get('id')
            q = re.sub(o,'',q)
            data_dict['q'] = q 
        return data_dict

    def _validator(self, pkg_id):
        GET_URI = 'https://api.iatistandard.org/validator/report'
        headers = {"Ocp-Apim-Subscription-Key": config.get('ckanext.iati.validator_key')}
        try:
            iati_validator_response = requests.get(GET_URI, params={'id':pkg_id}, headers=headers, timeout=TIMEOUT)
            summary = iati_validator_response.json()['report']['summary']
            if summary['critical'] > 0:
                return 'Critical'
            elif summary['error'] > 0:
                return 'Error'
            elif summary['warning'] > 0:
                return 'Warning'
            else:
                return 'Success'

        except Exception as e:
            log.error("EXCEPTION in validator: %s %s", type(e),e)

        return 'Not Found'


    def before_index(self, data_dict):
        # Add nicely formatted values for faceting
        fields = (
            ('country', iati_helpers.get_country_title),
            ('publisher_country', iati_helpers.get_country_title),
            ('publisher_source_type', iati_helpers.get_publisher_source_type_title),
            ('filetype', iati_helpers.get_file_type_title),
            ('publisher_organization_type', iati_helpers.get_organization_type_title),
            ('issue_type', iati_helpers.get_issue_title)
        )

        for name, func in fields:
            if data_dict.get('extras_{0}'.format(name)):
                data_dict[name] = func(data_dict['extras_{0}'.format(name)])

        try:
            _organization_title = json.loads(data_dict['data_dict'])['organization']['title']
            data_dict['extras_org_title'] = _organization_title
        except Exception as e:
            log.error(e)
            pass

        validation_status = self._validator(data_dict['id'])
        data_dict['extras_validation_status'] = validation_status
        validated_data_dict = json.loads(data_dict['validated_data_dict'])
        validated_data_dict['extras'].append({'key':'validation_status', 'value':validation_status})
        data_dict['validated_data_dict'] = json.dumps(validated_data_dict)

        return data_dict

    ## IConfigurer
    def update_config(self, config):
        if not config.get('ckan.site_url'):
            raise Exception('This extension requires site_url to be set up in the ini file')

        p.toolkit.add_template_directory(config, 'theme/templates')

    ## ITemplateHelpers
    def get_helpers(self):

        function_names = (
            'get_countries',
            'get_publisher_source_types',
            'get_publisher_frequencies',
            'get_licenses',
            'get_organization_types',
            'is_route_active',
            'get_country_title',
            'get_file_type_title',
            'get_publisher_source_type_title',
            'get_publisher_frequency_title',
            'get_organization_type_title',
            'get_issue_title',
            'get_publisher_extra_fields',
            'normalize_publisher_name',
            'return_select_options',
            'get_config_option',
            'check_nav_dropdown',
            'get_num_active_publishers',
            'SI_number_span',
            'format_file_size',
            'extras_to_dict',
            'publishers_pagination',
            'get_global_facet_items_dict',
            'get_global_search_facets',
            'urlencode',
            'organization_list',
            'get_first_published_date',
            'render_first_published_date',
            'organization_list_pending',
            'get_publisher_obj_extra_fields',
            'get_publisher_obj_extra_fields_pub_ids',
            'dataset_follower_count',
            'radio',
            'check_publisher_contact_email',
            'organizations_available_with_extra_fields',
            'structured_data_markup',
            'email_validator',
            'get_user_list_by_email',
            'first_published_date_patch',
            'organization_form_read_only',
            'get_publisher_list_download_formats',
            'get_archiver_status',
            'linked_user',
            'get_helper_text_popover_to_form',
            'search_country_list',
        )
        return _get_module_functions(iati_helpers, function_names)

    ## IActions
    def get_actions(self):
        import ckanext.iati.logic.action as iati_actions

        function_names = (
            'package_create',
            'package_update',
            'package_patch',
            'organization_create',
            'organization_update',
            'issues_report_csv',
            'group_list',
            'group_show',
            'organization_list',
            'organization_list_pending',
            'user_show',
            'user_list',
            'user_create',
            'organization_show',
            'resource_delete'
        )
        return _get_module_functions(iati_actions, function_names)

    ## IAuthFunctions
    def get_auth_functions(self):
        from ckanext.iati.logic import auth as iati_auth

        function_names = (
            'package_create',
            'package_update',
            'issues_report_csv'
        )
        return _get_module_functions(iati_auth, function_names)

    # Validators
    def get_validators(self):
        return {
            'not_empty': not_empty,
            'not_missing': not_missing,
            'email_validator': email_validator
        }


def _get_module_functions(module, function_names):
    functions = {}
    for f in function_names:
        functions[f] = module.__dict__[f]

    return functions


class IatiTheme(p.SingletonPlugin):

    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.IFacets, inherit=True)
    p.implements(p.IClick)

    # IRoutes
    def before_map(self, map):
        map.redirect('/about-2', '/about', _redirect_code='301 Moved Permanently')
        return map

    # IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')
        p.toolkit.add_public_directory(config, 'theme/public')
        p.toolkit.add_resource('assets', 'ckanext-iati')
        p.toolkit.add_public_directory(config, 'assets/')

    # IFacets
    def dataset_facets(self, facets_dict, package_type):
        ''' Update the facets_dict and return it. '''

        # We will actually remove all the core facets and add our own
        facets_dict.clear()

        facets_dict['publisher_source_type'] = p.toolkit._('Source')
        facets_dict['secondary_publisher'] = p.toolkit._('Secondary Publisher')
        facets_dict['organization'] = p.toolkit._('Publisher')
        facets_dict['publisher_country'] = p.toolkit._('Publisher Country')
        facets_dict['publisher_organization_type'] = p.toolkit._('Organisation Type')
        facets_dict['country'] = p.toolkit._('Recipient Country')
        facets_dict['filetype'] = p.toolkit._('File Type')
        if p.toolkit.c.userobj and p.toolkit.c.userobj.sysadmin:
            facets_dict['issue_type'] = p.toolkit._('Issue')

        return facets_dict

    def organization_facets(self, facets_dict, organization_type, package_type):
        ''' Update the facets_dict and return it. '''

        # We will actually remove all the core facets and add our own
        facets_dict.clear()
        facets_dict['publisher_source_type'] = p.toolkit._('Source')
        facets_dict['country'] = p.toolkit._('Recipient Country')
        facets_dict['filetype'] = p.toolkit._('File Type')

        if p.toolkit.c.userobj and p.toolkit.c.userobj.sysadmin:
            facets_dict['issue_type'] = p.toolkit._('Issues')

        return facets_dict

    def get_commands(self):
        from . import commands
        return commands.cmds
