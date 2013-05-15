from pylons.i18n import  _
from ckan.lib.base import c, request, config, h, redirect
from ckan.lib.helpers import json
from ckan import model
from ckan.controllers.package import PackageController
from ckan.authz import Authorizer

from ckan.logic import get_action
from ckan.logic.schema import package_form_schema
from ckan.lib.navl.validators import (ignore_missing,
                                      ignore_empty,
                                      not_empty,
                                      empty,
                                      ignore,
                                      keep_extras,
                                     )
from ckan.logic.validators import int_validator
from ckan.logic.converters import convert_from_extras, convert_to_extras, date_to_db, date_to_form

from ckanext.iati.lists import COUNTRIES
from ckanext.iati.logic.validators import iati_dataset_name, db_date, strip
from ckanext.iati.logic.converters import convert_from_comma_list, convert_to_comma_list, checkbox_value

class PackageIatiController(PackageController):

    package_form = 'package/form_iati.html'

    def _setup_template_variables(self, context, data_dict=None):

        super(PackageIatiController,self)._setup_template_variables(context,data_dict)

        c.groups_authz = self.get_groups()
        c.groups_available = self.get_groups(available_only=True)

        c.countries = [(v, k) for k, v in COUNTRIES]

    def _form_to_db_schema(self):
        schema = package_form_schema()
        schema.update({
            'filetype': [convert_to_extras],
            'country': [convert_to_extras, ignore_missing],
            'data_updated': [ignore_missing, ignore_empty, db_date, convert_to_extras],
            'activity_period-from': [ignore_missing, ignore_empty, db_date, convert_to_extras],
            'activity_period-to': [ignore_missing, ignore_empty, db_date, convert_to_extras],
            'activity_count': [int_validator,convert_to_extras,ignore_missing],
            'archive_file': [checkbox_value, convert_to_extras,ignore_missing],
            'verified': [checkbox_value, convert_to_extras,ignore_missing],
            'language': [convert_to_extras, ignore_missing],
            'secondary_publisher': [strip, convert_to_extras, ignore_missing],
            'issue_type': [convert_to_extras, ignore_missing],
            'issue_message': [convert_to_extras, ignore_missing],
            'issue_date': [convert_to_extras, ignore_missing],
        })

        schema['name'].append(iati_dataset_name)

        return schema

    def _db_to_form_schema(self):
        schema = package_form_schema()
        schema.update({
            'filetype': [convert_from_extras, ignore_missing],
            'country': [convert_from_extras, ignore_missing],
            'data_updated': [convert_from_extras,ignore_missing],
            'activity_period-from': [convert_from_extras,ignore_missing],
            'activity_period-to': [convert_from_extras,ignore_missing],
            'activity_count': [convert_from_extras,ignore_missing],
            'archive_file': [convert_from_extras,ignore_missing],
            'verified': [convert_from_extras,ignore_missing],
            'language': [convert_from_extras, ignore_missing],
            'secondary_publisher': [convert_from_extras, ignore_missing],
            'issue_type': [convert_from_extras, ignore_missing],
            'issue_message': [convert_from_extras, ignore_missing],
            'issue_date': [convert_from_extras, ignore_missing],

        })
        # Remove isodate validator
        schema['resources'].update({
            'last_modified': [ignore_missing],
            'cache_last_updated': [ignore_missing],
            'webstore_last_updated': [ignore_missing]
        })

        return schema

    def _check_data_dict(self, data_dict):
        return

    def _form_save_redirect(self, pkgname, action):
        '''This redirects the user to the CKAN package/read page,
        unless there is request parameter giving an alternate location,
        perhaps an external website.
        @param pkgname - Name of the package just edited
        @param action - What the action of the edit was
        '''
        assert action in ('new', 'edit')
        if action == 'new':
            msg = _('IATI Record created')
            h.flash_success(msg,allow_html=True)

        url = request.params.get('return_to') or \
              config.get('package_%s_return_url' % action)
        if url:
            url = url.replace('<NAME>', pkgname)
        else:
            url = h.url_for(controller='package', action='read', id=pkgname)
        redirect(url)

    # End hooks

    def get_groups(self,available_only=False):

        query = Authorizer().authorized_query(c.user, model.Group, model.Action.EDIT)
        groups = set(query.all())

        if available_only:
            package = c.pkg
            if package:
                groups = groups - set(package.groups)
        groups = [{'id':group.id,'name':group.name, 'title':group.title} for group in groups if group.state==model.State.ACTIVE]
        return sorted(groups, key=lambda k : k['title'])


