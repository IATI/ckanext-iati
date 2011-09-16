from pylons.i18n import  _
from ckan.lib.base import c, request, config, h, redirect
from ckan.lib.helpers import json
from ckan import model
from ckan.controllers.package import PackageController
from ckan.authz import Authorizer

from ckan.logic.schema import package_form_schema
from ckan.lib.navl.validators import (ignore_missing,
                                      not_empty,
                                      empty,
                                      ignore,
                                      keep_extras,
                                     )
from ckan.logic.converters import convert_from_extras, convert_to_extras, date_to_db, date_to_form
from ckan.lib.navl.dictization_functions import Missing, Invalid
from ckan.lib.field_types import DateType, DateConvertError

from countries import COUNTRIES

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
            'department': [unicode,convert_to_extras,ignore_missing],
            'filetype': [convert_to_extras],
            'country': [convert_to_extras, ignore_missing],
            'donors': [unicode, convert_from_comma_list, convert_to_extras, ignore_missing],
            'donors_type': [unicode, convert_from_comma_list, convert_to_extras, ignore_missing],
            'donors_country': [unicode, convert_from_comma_list, convert_to_extras, ignore_missing],
            'record_updated': [date_to_db, convert_to_extras,ignore_missing],
            'data_updated': [date_to_db, convert_to_extras,ignore_missing],
            'activity_period-from': [date_to_db, convert_to_extras,ignore_missing],
            'activity_period-to': [date_to_db, convert_to_extras,ignore_missing],
            'activity_count': [integer,convert_to_extras,ignore_missing],
            'archive_file': [checkbox_value, convert_to_extras,ignore_missing],
            'verified': [checkbox_value, convert_to_extras,ignore_missing],
        })

        return schema

    def _db_to_form_schema(self):
        schema = package_form_schema()
        schema.update({
            'department': [convert_from_extras,ignore_missing],
            'filetype': [convert_from_extras, ignore_missing],
            'country': [convert_from_extras, ignore_missing],
            'donors': [ignore_missing, convert_from_extras, convert_to_comma_list],
            'donors_type': [ignore_missing, convert_from_extras, convert_to_comma_list],
            'donors_country': [ignore_missing, convert_from_extras, convert_to_comma_list],
            'record_updated': [convert_from_extras,ignore_missing, date_to_form],
            'data_updated': [convert_from_extras,ignore_missing, date_to_form],
            'activity_period-from': [convert_from_extras,ignore_missing, date_to_form],
            'activity_period-to': [convert_from_extras,ignore_missing, date_to_form],
            'activity_count': [convert_from_extras,ignore_missing],
            'archive_file': [convert_from_extras,ignore_missing],
            'verified': [convert_from_extras,ignore_missing],
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

        return [{'id':group.id,'name':group.name, 'title':group.title} for group in groups if group.state==model.State.ACTIVE]


def convert_to_comma_list(value, context):
     
    return ', '.join(json.loads(value))

def convert_from_comma_list(value, context):
     
    return [x.strip() for x in value.split(',') if len(x)]

def checkbox_value(value,context):

    return 'yes' if not isinstance(value, Missing) else 'no'

def integer(value,context):

    if not value == '':
        try:
            value = int(value)
        except ValueError,e:
            raise Invalid(str(e))
        return value

