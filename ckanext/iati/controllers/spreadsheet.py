import logging
import csv
import StringIO

from ckan import model
from ckan.lib.base import c, request, response, config, h, redirect, render, abort,  BaseController
from ckan.lib.helpers import json
from ckan.authz import Authorizer
from ckan.logic import get_action, NotFound, ValidationError, NotAuthorized
from ckan.logic.converters import date_to_db
from ckan.logic.validators import int_validator
from ckan.lib.navl.validators import not_empty, ignore_empty
from ckan.lib.navl.dictization_functions import validate
from ckanext.iati.authz import get_user_administered_groups

from ckanext.iati.logic.validators import (iati_dataset_name_from_csv, 
                                           file_type_validator,
                                           db_date,
                                           yes_no,
                                           country_code)

log = logging.getLogger(__name__)

CSV_MAPPING = [
        ('registry-publisher-id', 'groups', 'name', [not_empty]),
        ('registry-file-id', 'package', 'name', [not_empty, iati_dataset_name_from_csv]),
        ('title', 'package', 'title', []),
        ('contact-email', 'package', 'author_email', []),
        ('source-url', 'resources', 'url', []),
        ('format', 'resources', 'format', []),
        ('file-type','extras', 'filetype', [ignore_empty, file_type_validator]),
        ('recipient-country','extras', 'country', [ignore_empty, country_code]),
        ('activity-period-start','extras', 'activity_period-from', [ignore_empty, db_date]),
        ('activity-period-end','extras', 'activity_period-to', [ignore_empty, db_date]),
        ('last-updated-datetime','extras', 'data_updated', [ignore_empty, db_date]),
        ('generated-datetime','extras', 'record_updated', [ignore_empty, db_date]),
        ('activity-count','extras', 'activity_count', [ignore_empty,int_validator]),
        ('verification-status','extras', 'verified', [ignore_empty,yes_no]),
        ('default-language','extras', 'language', [])
        ]

class CSVController(BaseController):


    def __before__(self, action, **params):
        super(CSVController,self).__before__(action, **params)

        if not c.user:
            abort(403,'Permission denied')

        self.is_sysadmin = Authorizer().is_sysadmin(c.user)

        # Groups of which the logged user is admin
        self.authz_groups = get_user_administered_groups(c.user)

    def download(self,publisher=None):

        context = {'model':model,'user': c.user or c.author}

        if publisher and publisher != 'all':
            try:
                group = get_action('group_show')(context, {'id':publisher})
            except NotFound:
                abort(404, 'Publisher not found')

            if not group['id'] in self.authz_groups and not self.is_sysadmin:
                abort(403,'Permission denied for this publisher group')

        if self.is_sysadmin:
            if publisher:
                # Return CSV for provided publisher
                output = self.write_csv_file(publisher)
            else:
                # Show list of all available publishers
                c.groups = get_action('group_list')(context, {'all_fields':True})
                return render('csv/index.html')
        else:
            if publisher and publisher != 'all':
                # Return CSV for provided publisher (we already checked the permissions)
                output = self.write_csv_file(publisher)
            elif len(self.authz_groups) == 1:
                # Return directly CSV for publisher
                output = self.write_csv_file(self.authz_groups[0])
            elif len(self.authz_groups) > 1:
                # Show list of available publishers for this user
                groups = get_action('group_list')(context, {'all_fields':True})
                c.groups = []
                for group in groups:
                    if group['id'] in self.authz_groups:
                        c.groups.append(group)

                return render('csv/index.html')
            else:
                # User does not have permissions on any publisher
                abort(403,'Permission denied')


        file_name = publisher if publisher else self.authz_groups[0]
        response.headers['Content-type'] = 'text/csv'
        response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % str(file_name)
        return output

    def upload(self):
        if not self.is_sysadmin and not self.authz_groups:
            # User does not have permissions on any publisher
            abort(403,'Permission denied')

        if request.method == 'GET':
            return render('csv/upload.html')
        elif request.method == 'POST':
            csv_file = request.POST['file']
            c.file_name = csv_file.filename

            added, updated, errors = self.read_csv_file(csv_file)
            c.added = added
            c.updated = updated

            c.errors = errors

            log.info('CSV import finished: file %s, %i added, %i updated, %i errors' % \
                    (c.file_name,len(c.added),len(c.updated),len(c.errors)))

            return render('csv/result.html')

    def write_csv_file(self,publisher):
        context = {'model':model,'user': c.user or c.author}
        try:
            if publisher == 'all':
                packages = get_action('package_list')(context, {})
            else:
                group = get_action('group_show')(context, {'id':publisher})
                packages = [pkg['id'] for pkg in group['packages']]
        except NotFound:
            abort(404, 'Group not found')

        f = StringIO.StringIO()

        output = ''
        try:
            fieldnames = [n[0] for n in CSV_MAPPING]
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            headers = dict( (n[0],n[0]) for n in CSV_MAPPING )
            writer.writerow(headers)

            packages.sort()
            for pkg in packages:
                try:
                    package = get_action('package_show_rest')(context,{'id':pkg})
                except NotAuthorized:
                    log.warn('User %s not authorized to read package %s' % (c.user, pkg))
                    continue
                if package:
                    row = {}
                    for fieldname, entity, key, v in CSV_MAPPING:
                        value = None
                        if entity == 'groups':
                            if len(package['groups']):
                                value = package['groups'][0]
                        elif entity == 'resources':
                            if len(package['resources']) and key in package['resources'][0]:
                                value = package['resources'][0][key]
                        elif entity == 'extras':
                            if key in package['extras']:
                                value = package['extras'][key]
                        else:
                            if key in package:
                                value = package[key]
                        row[fieldname] = value
                    writer.writerow(row)
            output = f.getvalue()
        finally:
            f.close()

        return output

    def read_csv_file(self,csv_file):
        fieldnames = [f[0] for f in CSV_MAPPING]

        # Try to sniff the file dialect
        dialect = csv.Sniffer().sniff(csv_file.file.read(1024))
        csv_file.file.seek(0)
        reader = csv.DictReader(csv_file.file, dialect=dialect)

        log.debug('Starting reading file %s (delimiter "%s", escapechar "%s")' %
                    (csv_file.filename,dialect.delimiter,dialect.escapechar))

        context = {'model':model,'user': c.user or c.author, 'api_verion':'1'}
        groups= get_action('group_list')(context, {})

        counts = {'added': [], 'updated': []}
        errors = {}
        for i,row in enumerate(reader):
            row_index = str(i + 1)
            errors[row_index] = {}
            try:
                # We will now run the IATI specific validation, CKAN core will
                # run the default one later on
                schema = dict([(f[0],f[3]) for f in CSV_MAPPING])
                row, row_errors = validate(row,schema)
                if row_errors:
                    for key, msgs in row_errors.iteritems():
                        log.error('Error in row %i: %s: %s' % (i+1,key,str(msgs)))
                        errors[row_index][key] = msgs
                    continue

                package_dict = self.get_package_dict_from_row(row)
                self.create_or_update_package(package_dict,counts)

                del errors[row_index]
            except ValidationError,e:
                iati_keys = dict([(f[2],f[0]) for f in CSV_MAPPING])
                for key, msgs in e.error_dict.iteritems():
                    iati_key = iati_keys[key]
                    log.error('Error in row %i: %s: %s' % (i+1,iati_key,str(msgs)))
                    errors[row_index][iati_key] = msgs
            except NotAuthorized,e:
                msg = 'Not authorized to publish to this group: %s' % row['registry-publisher-id']
                log.error('Error in row %i: %s' % msg)
                errors[row_index]['registry-publisher-id'] = [msg]

        errors = sorted(errors.iteritems())
        return counts['added'], counts['updated'], errors

    def get_package_dict_from_row(self,row):
        package = {}
        for fieldname, entity, key, v in CSV_MAPPING:
            if fieldname in row:
                # If value is None (empty cell), property will be set to blank
                value = row[fieldname]
                if entity == 'groups':
                    package['groups'] = [value]
                elif entity == 'resources':
                    if not 'resources' in package:
                       package['resources'] = [{}]
                    package['resources'][0][key] = value
                elif entity == 'extras':
                    if not 'extras' in package:
                       package['extras'] = {}
                    package['extras'][key] = value
                else:
                    package[key] = value
        return package

    def create_or_update_package(self, package_dict, counts = None):

        context = {
            'model': model,
            'session': model.Session,
            'user': c.user,
            'api_version':'1'
        }

        # Check if package exists
        data_dict = {}
        data_dict['id'] = package_dict['name']
        try:
            existing_package_dict = get_action('package_show')(context, data_dict)

            # Update package
            log.info('Package with name "%s" exists and will be updated' % package_dict['name'])

            context.update({'id':existing_package_dict['id']})
            package_dict.update({'id':existing_package_dict['id']})
            updated_package = get_action('package_update_rest')(context, package_dict)
            if counts:
                counts['updated'].append(updated_package['name'])
            log.debug('Package with name "%s" updated' % package_dict['name'])
        except NotFound:
            # Package needs to be created
            log.info('Package with name "%s" does not exist and will be created' % package_dict['name'])
            new_package = get_action('package_create_rest')(context, package_dict)
            if counts:
                counts['added'].append(new_package['name'])
            log.debug('Package with name "%s" created' % package_dict['name'])

