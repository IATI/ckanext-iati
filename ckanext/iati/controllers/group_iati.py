from ckan.lib.base import c
from ckan import model

from ckan.lib.navl.validators import ignore_missing, not_empty

from ckan.logic.schema import group_form_schema
from ckan.logic.converters import convert_from_extras, convert_to_extras
from ckan.controllers.group import GroupController

PUBLISHER_TYPES = ['Primary source', 'Secondary source']


class GroupIatiController(GroupController):

    group_form = 'group/form_iati.html'

    def _setup_template_variables(self, context):

        super(GroupIatiController,self)._setup_template_variables(context)

        c.licences = [('', '')] + model.Package.get_license_options()

    def _form_to_db_schema(self):
        schema = group_form_schema()
        schema.update({
            'type': [not_empty, publisher_type_validator, convert_to_extras],
            'license_id': [convert_to_extras],
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
        })

        return schema

    def _db_to_form_schema(self):
        schema = group_form_schema()
        schema.update({
            'type': [convert_from_extras],
            'license_id': [convert_from_extras],
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
        })

        return schema

    def _check_data_dict(self, data_dict):
        return


def publisher_type_validator(value,context):
    if not value in PUBLISHER_TYPES:
        raise Invalid('Unknown publisher type, allowed values: [%s]' % ', '.join(PUBLISHER_TYPES))
    return value
