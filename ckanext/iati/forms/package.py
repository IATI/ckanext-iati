# -*- coding: UTF-8 -*-
import formalchemy
from formalchemy import helpers as h
from sqlalchemy.util import OrderedDict
from pylons.i18n import _, ungettext, N_, gettext

from ckan.lib.helpers import literal
import ckan.forms.common as common
from ckan.forms.common import fa_h, TextExtraField, RegExRangeValidatingField, GroupSelectField
import ckan.model as model
import ckan.forms.package as package
from ckan.lib import field_types

from countries import COUNTRIES

__all__ = ['get_iati_fieldset']

class CommaListExtraField(RegExRangeValidatingField):
    '''A form field for two TextType fields, representing a range,
    stored in 'extra' fields.'''
    def get_configured(self):
        field = self.CommaListField(self.name).with_renderer(self.CommaListRenderer)
        return RegExRangeValidatingField.get_configured(self, field)

    class CommaListField(formalchemy.Field):
        def sync(self):
            if not self.is_readonly():
                pkg = self.model
                vals = self._deserialize() or []
                #vals = [v.strip()for v in vals.split(',') if len(v.strip())]
                pkg.extras[self.name] = vals

    class CommaListRenderer(formalchemy.fields.FieldRenderer):
        def _get_value(self):
            if self.value:
                return self.value
            extras = self.field.parent.model.extras
            return extras.get(self.field.name, [])

        def render(self, **kwargs):
            values = self._get_value()
            html = fa_h.text_field(self.name, value=', '.join(values), **kwargs)
            return html

        def render_readonly(self, **kwargs):
            val = ', '.join(self._get_value())
            return field_readonly_renderer(self.field.key, val_str)

        def _serialized_value(self):
            param_val = self.params.get(self.name, u'')
            return [v.strip()for v in param_val.split(',') if len(v.strip())]
            
        def deserialize(self):
            return self._serialized_value()


class SelectExtraField(TextExtraField):
    '''A form field for text from from a list of options, that is
    stored in an "extras" field.'''
    def __init__(self, name, options):
        self.options = options[:]
        # ensure options have key and value, not just a value
        for i, option in enumerate(self.options):
            if not isinstance(option, (tuple, list)):
                self.options[i] = (option, option)
        super(SelectExtraField, self).__init__(name)

    def get_configured(self):
        return self.TextExtraField(self.name, options=self.options).with_renderer(self.SelectRenderer)

    class SelectRenderer(formalchemy.fields.FieldRenderer):
        def _get_value(self, **kwargs):
            extras = self.field.parent.model.extras
            return unicode(kwargs.get('selected', '') or self.value or extras.get(self.field.name, ''))

        def render(self, options, **kwargs):
            selected = self._get_value()
            options = [('', '')] + options
            option_keys = [key for value, key in options]
            if selected in option_keys:
                select_field_selected = selected
            else:
                select_field_selected = u''
            fa_version_nums = formalchemy.__version__.split('.')
            # Requires FA 1.3.2 onwards for this select i/f
            html = literal(fa_h.select(self.name, select_field_selected, options, **kwargs))
                
            return html

        def render_readonly(self, **kwargs):
            return field_readonly_renderer(self.field.key, self._get_value())

        def _serialized_value(self):
            main_value = self.params.get(self.name, u'')
            return main_value

class AtLeastOneGroupSelectField(GroupSelectField):
    
    def get_configured(self):
        field = self.GroupSelectionField(self.name, self.allow_empty).with_renderer(self.GroupSelectEditRenderer)
        field.set(multiple=self.multiple)
        field = field.validate(self.validate_groups)
        field.user_editable_groups = self.user_editable_groups
        return field
        
    def validate_groups(self, val, field):
        if len(val) < 1:
            raise formalchemy.ValidationError(_("Need at least one publishing entity assigned"))

            
# Setup the fieldset
def build_package_iati_form(is_admin=False, user_editable_groups=None):
    builder = package.build_package_form(is_admin=is_admin, 
                                         user_editable_groups=user_editable_groups)
    
    # IATI specifics
    
    #Publishing Entity: 
    builder.add_field(AtLeastOneGroupSelectField('groups', allow_empty=False, 
                      user_editable_groups=user_editable_groups))
    
    #builder.add_field(common.TextExtraField('publisher'))
    #builder.set_field_text('publisher', _('Publishing entity'))
    
    #Publishing Entity Type: (Donor, Recipient, Community Data..)
    #builder.add_field(SelectExtraField('publisher_type', options=PUBLISHER_TYPES))
    #builder.set_field_text('publisher_type', _('Publishing entity type'))
    
    #Donor (TODO: Generate from crawler)   
    # Editable List, CSV? 
    builder.add_field(CommaListExtraField('donors'))
    builder.set_field_text('donors', _('Donors'), "Separate multiple entries using commas.")
    
    builder.add_field(CommaListExtraField('donors_type'))
    builder.set_field_text('donors_type', _('Donor type'), "Separate multiple entries using commas.")
    
    builder.add_field(CommaListExtraField('donors_country'))
    builder.set_field_text('donors_country', _('Donor country'), "Separate multiple entries using commas.")
    
    # TODO: Enforce validation
    countries = [(v, k) for k, v in COUNTRIES]
    builder.add_field(SelectExtraField('country', options=countries))
    builder.set_field_text('country', _('Recipient country'))
    
    #Verification status: enumeration of statuses (checked, not checked etc)
    # TODO: Enforce validation, can probably only be set by admins
    builder.add_field(common.CheckboxExtraField('verified'))
    builder.set_field_text('verified', _('Verification'))
    
    builder.add_field(common.CheckboxExtraField('archive_file'))
    builder.set_field_text('archive_file', _('Archive'))
    
    #Activity period: (Generate from crawler) 
    builder.add_field(common.DateRangeExtraField('activity_period'))
    builder.set_field_text('activity_period', _('Activitiy Period'))
    
    #Resource links: to the actual IATI record
    #Number of activities: (Generate from crawler) 
    builder.add_field(common.TextExtraField('activity_count'))
    builder.set_field_text('activity_count', _('Num. Activities'))
    
    #Date record updated:
    builder.add_field(common.TextExtraField('record_updated'))
    builder.set_field_text('record_updated', _('Record updated'))
    
    #Date data updated: 
    builder.add_field(common.TextExtraField('data_updated'))
    builder.set_field_text('data_updated', _('Data updated'))
    
    
    #License: Need this field even if it may be a standard license
    builder.add_field(common.TextExtraField('license'))
    builder.set_field_text('license', _('License'))
    
    #Department 
    # TODO: Make this a group property instead? 
    builder.add_field(common.TextExtraField('department'))
    builder.set_field_text('department', _('Department'))
    
    #Contact   
    builder.set_field_text('author', _('Contact'))
    
    #Contact e-mail
    builder.set_field_text('author_email', _('Contact e-mail'))
    
    #Licence    
    builder.set_field_text('license_id', _('License'))
    
    #Resource format    
    #Resource URL    
    #Resource ID    
    #  -- do we have an ID? 
    
    # Layout
    field_groups = OrderedDict([
        (_('Basic information'), ['name', 'title', 
                                  'author', 'author_email', 'department',]),
        (_('Publisher'), ['groups']),
        (_('Details'), ['country', 'donors', 'donors_type', 'donors_country',
                        'record_updated', 'data_updated',
                        'license_id', 'tags', 'notes']),
        (_('Resources'), ['resources']),
        (_('Verification and Analysis'), [
                        'activity_period', 
                        'activity_count', 'archive_file',
                              ]),
        ])
    if is_admin:
        field_groups[_('Verification and Analysis')].append('verified')
        field_groups[_('Verification and Analysis')].append('state')
    
    builder.set_displayed_fields(field_groups)
    
    return builder
    # Strings for i18n:
    [_('External reference'),  _('Date released'), _('Date updated'),
     _('Update frequency'), _('Geographic granularity'),
     _('Geographic coverage'), _('Temporal granularity'),
     _('Temporal coverage'), _('Categories'), _('National Statistic'),
     _('Precision'), _('Taxonomy URL'), _('Department'), _('Agency'), 
     ]

def get_package_fieldset(is_admin=False, user_editable_groups=None):
    return build_package_iati_form(is_admin=is_admin, 
                                   user_editable_groups=user_editable_groups).get_fieldset()
    
