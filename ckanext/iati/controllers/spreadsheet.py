import csv
import StringIO

from ckan import model
from ckan.lib.base import c, request, response, config, h, redirect, render, abort,  BaseController
from ckan.lib.helpers import json
from ckan.authz import Authorizer
from ckan.logic import get_action, NotFound
from ckanext.iati.patch import my_group

class CSVController(BaseController):

    csv_fieldnames = (
            'registry-publisher-id',
            'registry-file-id',
            'title',
            'contact-email',
            'source-url',
            'format',
            'file-type',
            'recipient-country',
            'activity-period-start',
            'activity-period-end',
            'last-updated-datetime',
            'generated-datetime',
            'activity-count',
            'verification-status',
            'default-language')

    def download(self,publisher=None):
        context = {'model':model,'user': c.user or c.author}
        is_sysadmin = Authorizer().is_sysadmin(c.user)
        user_group = my_group()

        if publisher:
            try:
                group = get_action('group_show')(context, {'id':publisher})
            except NotFound:
                abort(404, 'Group not found')
       
        if not user_group and not is_sysadmin:
            abort(403,'User does not belong to a publisher group')

        if is_sysadmin:
            if publisher:
                output = self.write_csv_file(publisher)
            else:
                c.groups = get_action('group_list')(context, {'all_fields':True})
                return render('csv/index.html')
        else:
            if publisher:
                if publisher == user_group.name:
                    output = self.write_csv_file(publisher)
                    return "COOL LETS DO IT with the provided publisher: %s" % publisher
                else:
                    abort(403,'Permission denied for this group')
            else:
                output = self.write_csv_file(user_group.name)                
        

        file_name = publisher if publisher else user_group.name
        response.headers['Content-type'] = 'text/csv'
        response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % file_name
        return output

    def upload(self):
        return "UPLOAD CSV"

    def write_csv_file(self,publisher):
        context = {'model':model,'user': c.user or c.author}
        try:
            group = get_action('group_show')(context, {'id':publisher})
        except NotFound:
            abort(404, 'Group not found')

        f = StringIO.StringIO()
        
        output = ''
        try:
            writer = csv.DictWriter(f, fieldnames=self.csv_fieldnames, quoting=csv.QUOTE_ALL)
            headers = dict( (n,n) for n in self.csv_fieldnames )
            writer.writerow(headers)
            for pkg in group['packages']:
                
                package = get_action('package_show_rest')(context,{'id':pkg['id']})
                
                extras = package['extras']
                writer.writerow({ 
                    'registry-publisher-id': group['name'],
                    'registry-file-id': package['name'],
                    'title': package['title'],
                    'contact-email': package['author_email'],
                    'source-url': package['resources'][0]['url'] if len(package['resources']) else None,
                    'format': package['resources'][0]['format'] if len(package['resources']) else None,
                    'file-type': extras['filetype'],
                    'recipient-country': extras['country'],
                    'activity-period-start': extras['activity_period-from'],
                    'activity-period-end': extras['activity_period-to'],
                    'last-updated-datetime': extras['data_updated'],
                    'generated-datetime': extras['record_updated'],
                    'activity-count': extras['activity_count'] if 'activity_count' in extras else None,
                    'verification-status': extras['verified'],
                    'default-language': extras['language']
                    })
            output = f.getvalue()
        finally:
            f.close()

        return output





