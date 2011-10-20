import csv
import StringIO

from ckan import model
from ckan.lib.base import c, request, response, config, h, redirect, render, abort,  BaseController
from ckan.lib.helpers import json
from ckan.authz import Authorizer
from ckan.logic import get_action, NotFound
from ckanext.iati.authz import get_user_administered_groups

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

    def download(self,publisher=None):
        if not c.user:
            abort(403,'Permission denied')

        context = {'model':model,'user': c.user or c.author}

        is_sysadmin = Authorizer().is_sysadmin(c.user)

        # Groups of which the logged user is admin
        authz_groups = get_user_administered_groups(c.user)

        if publisher and publisher != 'all':
            try:
                group = get_action('group_show')(context, {'id':publisher})
            except NotFound:
                abort(404, 'Publisher not found')

            if not group['id'] in authz_groups and not is_sysadmin:
                abort(403,'Permission denied for this publisher group')

        if is_sysadmin:
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
            elif len(authz_groups) == 1:
                # Return directly CSV for publisher
                output = self.write_csv_file(authz_groups[0])
            elif len(authz_groups) > 1:
                # Show list of available publishers for this user
                groups = get_action('group_list')(context, {'all_fields':True})
                c.groups = []
                for group in groups:
                    if group['id'] in authz_groups:
                        c.groups.append(group)

                return render('csv/index.html')
            else:
                # User does not have permissions on any publisher
                abort(403,'Permission denied')


        file_name = publisher if publisher else authz_groups[0]
        response.headers['Content-type'] = 'text/csv'
        response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % file_name
        return output

    def upload(self):
        return "UPLOAD CSV"

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





