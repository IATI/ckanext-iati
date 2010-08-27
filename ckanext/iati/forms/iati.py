# -*- coding: UTF-8 -*-
import formalchemy
from formalchemy import helpers as h
from sqlalchemy.util import OrderedDict
from pylons.i18n import _, ungettext, N_, gettext

from ckan.lib.helpers import literal
import ckan.forms.common as common
from ckan.forms.common import fa_h, TextExtraField
import ckan.model as model
import ckan.forms.package as package
from ckan.lib import field_types

from countries import COUNTRIES

__all__ = ['get_iati_fieldset']

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



# Setup the fieldset
def build_package_iati_form(is_admin=False):
    
    PUBLISHER_TYPES = [_("Donor"),
                       _("Recipient"),
                       _("Community")]
    
    builder = package.build_package_form()
    
    # IATI specifics
    
    # TODO Factor these out into group properties and enforce using authz
    #Publishing Entity: 
    builder.add_field(common.TextExtraField('publisher'))
    builder.set_field_text('publisher', _('Publishing entity'))
    
    #Publishing Entity Type: (Donor, Recipient, Community Data..)
    builder.add_field(SelectExtraField('publisher_type', options=PUBLISHER_TYPES))
    builder.set_field_text('publisher_type', _('Publishing entity type'))
    
    #Donor (TODO: Generate from crawler)   
    # Editable List, CSV? 
    builder.add_field(common.TextExtraField('donors'))
    
    # TODO: Enforce validation
    countries = [(v, k) for k, v in COUNTRIES]
    builder.add_field(SelectExtraField('country', options=countries))
    
    #Verification status: enumeration of statuses (checked, not checked etc)
    # TODO: Enforce validation, can probably only be set by admins
    builder.add_field(common.CheckboxExtraField('verified'))
    builder.set_field_text('verified', _('Verification'))
    
    #Activity period: (Generate from crawler) 
    builder.add_field(common.DateRangeExtraField('activity_period'))
    builder.set_field_text('activity_period', _('Activitiy Period'))
    
    
    #Resource links: to the actual IATI record
    #Number of activities: (Generate from crawler) 
    builder.add_field(common.TextExtraField('activity_count'))
    builder.set_field_text('activity_count', _('Number of Activities'))
    
    #Date record updated:
    builder.add_field(common.TextExtraField('record_updated'))
    builder.set_field_text('record_updated', _('Date record updated'))
    
    #Date data updated: 
    builder.add_field(common.TextExtraField('data_updated'))
    builder.set_field_text('data_updated', _('Date data updated'))
    
    
    #License: Need this field even if it may be a standard license
    builder.add_field(common.TextExtraField('license'))
    builder.set_field_text('license', _('License'))
    
    #Department 
    # TODO: Make this a group property instead? 
    builder.add_field(common.TextExtraField('department'))
    builder.set_field_text('verified', _('Department'))
    
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
        (_('TEMP: Publishing Entity Info'), ['publisher', 'publisher_type']),
        (_('Details'), ['donors', 'country', 'activity_period', 
                        'record_updated', 'data_updated',
                        'license_id', 'tags', 'notes']),
        (_('Resources'), ['resources']),
        (_('Verification and Analysis'), [
                        'activity_count'
                              ]),
        ])
    if is_admin:
        field_groups[_('Verification and Analysis')].append('state')
        field_groups[_('Verification and Analysis')].append('verified')
    
    builder.set_displayed_fields(field_groups)
    
    return builder
    # Strings for i18n:
    [_('External reference'),  _('Date released'), _('Date updated'),
     _('Update frequency'), _('Geographic granularity'),
     _('Geographic coverage'), _('Temporal granularity'),
     _('Temporal coverage'), _('Categories'), _('National Statistic'),
     _('Precision'), _('Taxonomy URL'), _('Department'), _('Agency'), 
     ]

fieldsets = {} # fieldset cache

def get_iati_fieldset(is_admin=False):
    '''Returns the standard fieldset
    '''
    if not fieldsets:
        # fill cache
        fieldsets['package_iati_fs'] = build_package_iati_form().get_fieldset()
        fieldsets['package_iati_fs_admin'] = build_package_iati_form(is_admin=True).get_fieldset()

    if is_admin:
        fs = fieldsets['package_iati_fs_admin']
    else:
        fs = fieldsets['package_iati_fs']
    return fs
