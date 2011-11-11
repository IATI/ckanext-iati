from ckan.lib.base import c,request
from ckan import model

from ckan.lib.navl.validators import ignore_missing, not_empty
from ckan.lib.navl.dictization_functions import Invalid

from ckan.logic.validators import ignore_not_admin
from ckan.logic.schema import group_form_schema
from ckan.logic.converters import convert_from_extras, convert_to_extras
from ckan.controllers.group import GroupController

from ckanext.iati.lists import ORGANIZATION_TYPES, COUNTRIES, PUBLISHER_SOURCE_TYPES

class GroupIatiController(GroupController):

    group_form = 'group/form_iati.html'

    def _setup_template_variables(self, context):

        super(GroupIatiController,self)._setup_template_variables(context)

        c.licences = [('', '')] + model.Package.get_license_options()

        c.organization_types = ORGANIZATION_TYPES
        c.publisher_source_types = PUBLISHER_SOURCE_TYPES
        c.countries = [(v, k) for k, v in COUNTRIES]

        c.show_publisher_info = not (request.environ['pylons.routes_dict']['action'] == 'authz')


    def _form_to_db_schema(self):
        schema = group_form_schema()
        schema.update({
            'state': [ignore_not_admin],
            'type': [not_empty, convert_to_extras],
            'license_id': [convert_to_extras],
            'publisher_iati_id': [convert_to_extras, ignore_missing],
            'publisher_country': [convert_to_extras, ignore_missing],
            'publisher_segmentation': [unicode, convert_to_extras, ignore_missing],
            'publisher_ui': [unicode, convert_to_extras, ignore_missing],
            'publisher_frequency': [unicode, convert_to_extras, ignore_missing],
            'publisher_thresholds': [unicode, convert_to_extras, ignore_missing],
            'publisher_units': [unicode, convert_to_extras, ignore_missing],
            'publisher_contact': [unicode, convert_to_extras, ignore_missing],
            'publisher_agencies': [unicode, convert_to_extras, ignore_missing],
            'publisher_field_exclusions': [unicode, convert_to_extras, ignore_missing],
            'publisher_description': [unicode, convert_to_extras, ignore_missing],
            'publisher_record_exclusions': [unicode, convert_to_extras, ignore_missing],
            'publisher_timeliness': [unicode, convert_to_extras, ignore_missing],
            'publisher_refs': [unicode, convert_to_extras, ignore_missing],
            'publisher_constraints': [unicode, convert_to_extras, ignore_missing],
            'publisher_data_quality': [unicode, convert_to_extras, ignore_missing],
            'publisher_organization_type': [unicode, convert_to_extras, ignore_missing],
        })

        return schema

    def _db_to_form_schema(self):
        schema = group_form_schema()
        schema.update({
            'state': [ignore_not_admin],
            'type': [convert_from_extras],
            'license_id': [convert_from_extras],
            'publisher_country': [convert_from_extras],
            'publisher_iati_id': [convert_from_extras, ignore_missing],
            'publisher_segmentation': [convert_from_extras],
            'publisher_ui': [convert_from_extras],
            'publisher_frequency': [convert_from_extras],
            'publisher_thresholds': [convert_from_extras],
            'publisher_units': [convert_from_extras],
            'publisher_contact': [convert_from_extras],
            'publisher_agencies': [convert_from_extras],
            'publisher_field_exclusions': [convert_from_extras],
            'publisher_description': [convert_from_extras],
            'publisher_record_exclusions': [convert_from_extras],
            'publisher_timeliness': [convert_from_extras],
            'publisher_refs': [convert_from_extras],
            'publisher_constraints': [convert_from_extras],
            'publisher_data_quality': [convert_from_extras],
            'publisher_organization_type': [convert_from_extras],
        })

        return schema

    def _check_data_dict(self, data_dict):
        return

