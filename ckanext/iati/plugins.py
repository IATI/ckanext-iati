import logging
from ckan.common import c
# Bad imports: this should be in the toolkit
import json
import os
from collections import OrderedDict
from flask import Blueprint, redirect
from ckan.lib.plugins import DefaultOrganizationForm
from ckanext.iati.views.archiver import ArchiverViewRun
import ckan.plugins as p
from ckanext.iati.logic.validators import (
    db_date,
    iati_publisher_state_validator,
    iati_owner_org_validator,
    iati_dataset_name,
    iati_resource_count,
    iati_resource_url,
    iati_one_resource,
    email_validator,
    file_type_validator,
    iati_org_identifier_validator,
    remove_leading_or_trailing_spaces,
    licence_validator,
    iati_resource_url_mandatory,
    country_code,
    change_publisher_id_or_org_id,
    first_publisher_date_validator,
    validate_new_publisher_id_against_old
)
from ckanext.iati.logic.converters import strip
import ckanext.iati.helpers as iati_helpers
from ckanext.iati.model import IATIRedirects
from ckanext.iati.views.publisher import publisher_blueprint
from ckanext.iati.views.reports import issues
from ckanext.iati.views.dashboard import custom_dashboard
from ckanext.iati.views.admin import admin_tabs
from ckanext.iati.views.helper_pages import helper_pages
from ckanext.iati.views.spreadsheet import spreadsheet
from ckanext.iati.views.archiver import archiver as archiver_blueprint

log = logging.getLogger(__name__)


class IatiPublishers(p.SingletonPlugin, DefaultOrganizationForm):

    p.implements(p.IBlueprint)
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

        # Custom redirects for publisher renames
        # Add a new line for each redirect, in the form
        #
        #   ('old_name', 'new_name',),
        # redirects.json file is located in redirects dir
        # Use commad paster --plugin=ckanext-iati iati-first-publisher-date update_redirects
        # To get all the latest renames

        renames = [
            ('amrefuk', 'amrefha',),
            ('ausaid', 'ausgov',),
            ('mrdf', 'allwecan',),
            ('unesco-ihe', 'ihedelft')
        ]

        _redirects = IATIRedirects.get_redirects()
        
        for row in _redirects:
            renames.append((row[2], row[1]))

        for rename in renames:
            # Publisher pages
            map.redirect('/publisher/' + rename[0], '/publisher/' + rename[1],
                         _redirect_code='301 Moved Permanently')
            map.redirect('/publisher/{url:.*}/' + rename[0] , '/publisher/{url}/' + rename[1],
                         _redirect_code='301 Moved Permanently')

            # Dataset pages
            map.redirect('/dataset/' + rename[0] + '-{code:.*}', '/dataset/' + rename[1] + '-{code:.*}',
                         _redirect_code='301 Moved Permanently')
            map.redirect('/dataset/{url:.*}/' + rename[0] + '-{code:.*}', '/dataset/{url}/' + rename[1] + '-{code:.*}',
                         _redirect_code='301 Moved Permanently')

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
        _name_validator = p.toolkit.get_validator('name_validator')
        _group_name_validator = p.toolkit.get_validator('group_name_validator')

        default_validators = [_ignore_missing, _convert_to_extras, str]
        schema.update({
            'state': [iati_publisher_state_validator],
            'title': [_not_empty, remove_leading_or_trailing_spaces],
            'name': [_not_empty, _unicode_safe, _name_validator, _group_name_validator, change_publisher_id_or_org_id,
                     validate_new_publisher_id_against_old],
            'license_id': [_convert_to_extras, licence_validator],
            'publisher_source_type': default_validators,
            'publisher_iati_id': [_not_empty, remove_leading_or_trailing_spaces, iati_org_identifier_validator,
                                  _convert_to_extras, str, change_publisher_id_or_org_id],
            'publisher_country': default_validators,
            'publisher_segmentation': default_validators,
            'publisher_ui': default_validators,
            'publisher_ui_url': [_ignore_missing, iati_resource_url, _convert_to_extras, str],
            'publisher_url': [_ignore_missing, iati_resource_url, _convert_to_extras, str],
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
            'publisher_organization_type': default_validators,
            'publisher_implementation_schedule': default_validators,
            'publisher_first_publish_date': [_ignore_missing, _convert_to_extras, str,
                                             first_publisher_date_validator]
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

    # IBlueprint
    def get_blueprint(self):
        blueprints = [publisher_blueprint, custom_dashboard, issues, admin_tabs, helper_pages, spreadsheet, archiver_blueprint]

        bp = Blueprint(u'iati_publishers_redirects', __name__)

        @bp.route('/group/<path:url>')
        def _r_group_url(url):
            return redirect('/publisher/{0}'.format(url), code=301)

        @bp.route('/group')
        def _r_group_root():
            return redirect('/publisher', code=301)

        @bp.route('/organization/<path:url>')
        def _r_org_url(url):
            return redirect('/publisher/{0}'.format(url), code=301)

        @bp.route('/organization')
        def _r_org_root():
            return redirect('/publisher', code=301)

        @bp.route('/publishers')
        def _r_publishers_root():
            return redirect('/publisher', code=301)

        @bp.route('/publishers/<path:url>')
        def _r_publishers_url(url):
            return redirect('/publisher/{0}'.format(url), code=301)

        @bp.route('/dataset_search')
        def _r_dataset_search():
            return redirect('/dataset', code=301)

        built_in = [
            ('amrefuk', 'amrefha'),
            ('ausaid', 'ausgov'),
            ('mrdf', 'allwecan'),
            ('unesco-ihe', 'ihedelft'),
        ]

        rename_map = OrderedDict((old, new) for (old, new) in built_in)

        try:
            _redirects = IATIRedirects.get_redirects()
            for row in _redirects:
                old, new = row[2], row[1]
                if old and new and old != new:
                    rename_map[old] = new
        except Exception:
            # Don't fail extension load if DB isn't ready at import time
            pass

        def _add_publisher_rename(old, new):
            # Publisher pages
            bp.add_url_rule(
                '/publisher/{0}'.format(old),
                endpoint='pub_{0}'.format(old),
                view_func=(lambda old=old, new=new: redirect('/publisher/{0}'.format(new), code=301))
            )
            bp.add_url_rule(
                '/publisher/<path:url>/{0}'.format(old),
                endpoint='pub_sub_{0}'.format(old),
                view_func=(lambda url, old=old, new=new: redirect('/publisher/{0}/{1}'.format(url, new), code=301))
            )
            # Dataset pages for that publisher prefix
            bp.add_url_rule(
                '/dataset/{0}-<code>'.format(old),
                endpoint='ds_pub_{0}'.format(old),
                view_func=(lambda code, old=old, new=new: redirect('/dataset/{0}-{1}'.format(new, code), code=301))
            )
            bp.add_url_rule(
                '/dataset/<path:url>/{0}-<code>'.format(old),
                endpoint='ds_pub_sub_{0}'.format(old),
                view_func=(lambda url, code, old=old, new=new: redirect('/dataset/{0}/{1}-{2}'.format(url, new, code), code=301))
            )

        for old, new in rename_map.items():
            _add_publisher_rename(old, new)

        @bp.route('/api/<ver>/rest/publisher')
        def _r_api_pub(ver):
            return redirect('/api/{0}/rest/group'.format(ver), code=301)

        @bp.route('/api/rest/publisher')
        def _r_api_pub_legacy():
            return redirect('/api/rest/group', code=301)

        @bp.route('/api/<ver>/rest/publisher/<path:url>')
        def _r_api_pub_url(ver, url):
            return redirect('/api/{0}/rest/group/{1}'.format(ver, url), code=301)

        @bp.route('/api/rest/publisher/<path:url>')
        def _r_api_pub_url_legacy(url):
            return redirect('/api/rest/group/{0}'.format(url), code=301)

        redirects = {
            '/using-iati-data': 'http://iatistandard.org/en/using-data/',
            '/registry-dashboard': 'http://iatistandard.org/en/guidance/publishing-data/data-quality-/how-to-improve-you-data-quality-with-the-iati-dashboard/',
            '/about': 'http://iatistandard.org/en/using-data/IATI-tools-and-resources/using-IATI-registry/',
            '/registry-api': 'http://iatistandard.org/en/using-data/IATI-tools-and-resources/using-IATI-registry/',
            '/help': 'http://iatistandard.org/en/guidance/preparing-organisation/organisation-account/how-to-register-with-iati/'
        }

        for k, v in redirects.items():
            endpoint_name = 'redir_' + (k.strip('/').replace('/', '_') or 'root')
            bp.add_url_rule(k, endpoint=endpoint_name, view_func=(lambda v=v: redirect(v, code=301)))

        blueprints.append(bp)
        return blueprints

class IatiDatasets(p.SingletonPlugin, p.toolkit.DefaultDatasetForm):

    p.implements(p.IBlueprint)
    p.implements(p.IDatasetForm, inherit=True)
    p.implements(p.IPackageController, inherit=True)
    p.implements(p.IConfigurer)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)

    def get_blueprint(self):
        bp = Blueprint(u'iati_datasets_redirects', __name__)

        @bp.route('/dataset/wb-<code>')
        def _r_wb(code):
            return redirect('/dataset/worldbank-{0}'.format(code), code=301)

        @bp.route('/dataset/minbuza_activities')
        def _r_minbuza_act():
            return redirect('/dataset/minbuza_nl-activities', code=301)

        @bp.route('/dataset/minbuza_organisation')
        def _r_minbuza_org():
            return redirect('/dataset/minbuza_nl-organisation', code=301)

        @bp.route('/feed/registry.atom')
        def _r_feed_registry():
            return redirect('/feeds/dataset.atom', code=301)

        @bp.route('/feed/publisher/<id>.atom')
        def _r_feed_publisher(id):
            return redirect('/feeds/group/{0}.atom'.format(id), code=301)

        @bp.route('/feed/custom.atom')
        def _r_feed_custom():
            return redirect('/feeds/custom.atom', code=301)

        @bp.route('/feed/country/<id>.atom')
        def _r_feed_country(id):
            return redirect('/feeds/custom.atom?extras_country={0}'.format(id), code=301)

        @bp.route('/feed/organisation_type/<id>.atom')
        def _r_feed_org_type(id):
            return redirect('/feeds/custom.atom?extras_publisher_organization_type={0}'.format(id), code=301)

        renames = [
            ('ciuk-org','ciuk-activity'),
            ('uncdf-org','uncdf-activity'),
            ('plan_uk-org210613','plan_uk-activity'),
            ('international-alert-org','international-alert-activity'),
            ('globalintegrity-org','globalintegrity-activity'),
        ]
        for old, new in renames:
            bp.add_url_rule(
                '/dataset/{0}'.format(old),
                endpoint='ds_{0}'.format(old),
                view_func=(lambda old=old, new=new: redirect('/dataset/{0}'.format(new), code=301))
            )
            bp.add_url_rule(
                '/dataset/<path:url>/{0}'.format(old),
                endpoint='ds_sub_{0}'.format(old),
                view_func=(lambda url, old=old, new=new: redirect('/dataset/{0}/{1}'.format(url, new), code=301))
            )
        return [bp]

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

        schema.update({
            'filetype': [_ignore_missing,file_type_validator, _convert_to_extras],
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

        schema['resources']['url'].extend([iati_resource_count, strip, iati_resource_url_mandatory])

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
            org = p.toolkit.get_action('organization_show')({}, {'id': data_dict['owner_org']})
            if org:
                new_extras = []
                for key in ('publisher_source_type', 'publisher_organization_type', 'publisher_country',
                            'publisher_iati_id',):
                    new_extras.append({'key': key, 'value': org.get(key, '')})

                data_dict['extras'].extend(new_extras)

                # Inherit license from publisher
                license = self._get_license_register().get(org.get('license_id'))
                if license:
                    data_dict['license_id'] = license.id
                    if license.url:
                        data_dict['license_url']= license.url
                    if license.title:
                        data_dict['license_title']= license.title
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
            log.info(pkg_dict.get('id', ''))
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

    def before_index(self, data_dict):

        # Add nicely formatted values for faceting
        fields = (
            ('country', iati_helpers.get_country_title),
            ('publisher_country', iati_helpers.get_country_title),
            ('publisher_source_type', iati_helpers.get_publisher_source_type_title),
            ('filetype', iati_helpers.get_file_type_title),
            ('publisher_source_type', iati_helpers.get_publisher_source_type_title),
            ('publisher_organization_type', iati_helpers.get_organization_type_title),
            ('issue_type', iati_helpers.get_issue_title)
        )

        for name, func in fields:
            if data_dict.get('extras_{0}'.format(name)):
                data_dict[name] = func(data_dict['extras_{0}'.format(name)])

        try:
            _organization_title = json.loads(data_dict['data_dict'])['organization']['title']
            data_dict[u'extras_org_title'] = _organization_title
        except Exception as e:
            log.error(e)
            pass
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
            'publisher_first_published_date_validator',
            'organization_form_read_only',
            'get_publisher_list_download_formats',
            'get_archiver_status'
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
            'resource_delete',
            'organization_patch'
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


def _get_module_functions(module, function_names):
    functions = {}
def _get_module_functions(module, function_names):
    functions = {}
    for f in function_names:
        functions[f] = module.__dict__[f]

    return functions


class IatiTheme(p.SingletonPlugin):

    p.implements(p.IBlueprint)
    p.implements(p.IConfigurer)
    p.implements(p.IFacets, inherit=True)

    # IRoutes
    def before_map(self, map):
        map.redirect('/about-2', '/about', _redirect_code='301 Moved Permanently')
        return map

    def get_blueprint(self):
        bp = Blueprint(u'iati_theme_redirects', __name__)

        @bp.route('/about-2')
        def _r_about_2():
            return redirect('/about', code=301)

        return [bp]

    # IConfigurer
    def update_config(self, config):
        p.toolkit.add_template_directory(config, 'theme/templates')
        p.toolkit.add_public_directory(config, 'theme/public')
        p.toolkit.add_resource('theme/fanstatic_library', 'ckanext-iati')

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
