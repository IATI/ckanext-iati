import logging
import csv
import StringIO

from ckan import model
from ckan.lib.base import c, request, response, config, h, redirect, render, abort,  BaseController
from ckan.lib.helpers import json
from ckan.authz import Authorizer
from ckan.logic import get_action, NotFound, ValidationError, NotAuthorized
from ckanext.iati.authz import get_user_administered_groups

log = logging.getLogger(__name__)


class CSVController(BaseController):

    csv_mapping = [
            ('registry-publisher-id', 'groups', 'name'),
            ('registry-file-id', 'package', 'name'),
            ('title', 'package', 'title'),
            ('contact-email', 'package', 'author_email'),
            ('source-url', 'resources', 'url'),
            ('format', 'resources', 'format'),
            ('file-type','extras', 'filetype'),
            ('recipient-country','extras', 'country'),
            ('activity-period-start','extras', 'activity_period-from'),
            ('activity-period-end','extras', 'activity_period-to'),
            ('last-updated-datetime','extras', 'data_updated'),
            ('generated-datetime','extras', 'record_updated'),
            ('activity-count','extras', 'activity_count'),
            ('verification-status','extras', 'verified'),
            ('default-language','extras', 'language')
            ]

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
        response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % file_name
        return output

    def upload(self):
        if request.method == 'GET':
            return render('csv/upload.html')
        elif request.method == 'POST':
            csv_file = request.POST['file']
            c.file_name = csv_file.filename

            added, updated, errors = self.read_csv_file(csv_file)
            c.added = added
            c.updated = updated
            c.errors = errors

            log.info('CSV export finished: file %s, %i added, %i updated, %i errors' % \
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
            fieldnames = [n[0] for n in self.csv_mapping]
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            headers = dict( (n[0],n[0]) for n in self.csv_mapping )
            writer.writerow(headers)

            packages.sort()
            for pkg in packages:

                package = get_action('package_show_rest')(context,{'id':pkg})
                if package:
                    row = {}
                    for fieldname, entity, key in self.csv_mapping:
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
        fieldnames = [n[0] for n in self.csv_mapping]
        #reader = csv.DictReader(csv_file.file,fieldnames=fieldnames)
        #TODO: separator
        reader = csv.DictReader(csv_file.file)

        context = {'model':model,'user': c.user or c.author, 'api_verion':'1'}
        groups= get_action('group_list')(context, {})

        counts = {'added': [], 'updated': []}
        errors = []
        for i,row in enumerate(reader):
            try:
                # Check mandatory fields
                if not row['registry-publisher-id']:
                     raise ValueError('Publisher not defined')

                if not row['registry-file-id']:
                    raise ValueError('File id not defined')

                # Check name convention
                name = row['registry-file-id']
                parts = name.split('-')
                group_name = parts[0] if len(parts) == 2 else '-'.join(parts[:-1])
                if not group_name or not group_name in groups:
                    raise ValueError('Dataset name does not follow the convention <publisher>-<code>: "%s"' % group_name)

                package_dict = self.get_package_dict_from_row(row)
                self.create_or_update_package(package_dict,counts)
            except ValueError,e:
                msg = 'Error in row %i: %s' % (i+1,str(e))
                log.error(msg)
                errors.append(msg)
            except NotAuthorized,e:
                msg = 'Error in row %i: Not authorized to publish to this group: %s' % (i+1,row['registry-publisher-id'])
                log.error(msg)
                errors.append(msg)

        return counts['added'], counts['updated'], errors

    def get_package_dict_from_row(self,row):
        package = {}
        for fieldname, entity, key in self.csv_mapping:
            if fieldname in row:
                value = row[fieldname]
                if value:
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
        try:

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
        except ValidationError,e:
            raise ValueError(str(e))




