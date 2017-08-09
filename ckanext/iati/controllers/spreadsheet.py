import logging
import csv
import StringIO
import uuid
import json
from collections import OrderedDict
import os
import routes
import urlparse

from ckan import model
import ckan.authz as authz
from ckan.lib.base import c
import ckan.plugins as p
from ckanext.iati.helpers import extras_to_dict
from ckan.lib.celery_app import celery


log = logging.getLogger(__name__)
_not_empty = p.toolkit.get_validator('not_empty')
_ignore_empty = p.toolkit.get_validator('ignore_empty')
_ignore_missing = p.toolkit.get_validator('ignore_missing')
_int_validator = p.toolkit.get_validator('int_validator')

CSV_MAPPING = [
        ('registry-publisher-id', 'organization', 'name'),
        ('registry-file-id', 'package', 'name'),
        ('title', 'package', 'title'),
        ('description', 'package', 'notes'),
        ('contact-email', 'package', 'author_email'),
        ('state', 'package', 'state'),
        ('source-url', 'resources', 'url'),
        ('format', 'resources', 'format'),
        ('file-type','package', 'filetype'),
        ('recipient-country','package', 'country'),
        ('last-updated-datetime','package', 'data_updated'),
        ('activity-count','package', 'activity_count'),
        ('default-language','package', 'language'),
        ('secondary-publisher', 'package', 'secondary_publisher'),
        ]

OPTIONAL_COLUMNS = ['state', 'description']

ckan_ini_filepath = os.environ.get('CKAN_CONFIG')


def _fix_unicode(text, min_confidence=0.5):
    import chardet
    guess = chardet.detect(text)
    if guess["confidence"] < min_confidence:
        raise UnicodeDecodeError
    text = unicode(text, guess["encoding"])
    text = text.encode('utf-8')
    return text


class CSVController(p.toolkit.BaseController):

    def download(self, publisher=None):

        context = {'model': model, 'user': c.user or c.author}

        if publisher and publisher not in ['all','template']:
            try:
                org = p.toolkit.get_action('organization_show')(context, {'id': publisher})
            except p.toolkit.ObjectNotFound:
                p.toolkit.abort(404, 'Publisher not found')

        if publisher:
            # Return CSV for provided publisher
            output = self.write_csv_file(publisher)
        else:
            # Show list of all available publishers
            orgs = p.toolkit.get_action('organization_list')(context, {'all_fields': True})
            return p.toolkit.render('csv/index.html', extra_vars={'orgs': orgs})

        file_name = publisher if publisher else 'iati-registry-records'
        p.toolkit.response.headers['Content-type'] = 'text/csv'
        p.toolkit.response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % str(file_name)
        return output

    def upload(self):
        from pylons import config

        if not c.user:
            p.toolkit.abort(401, 'Permission denied, only publisher administrators can manage CSV files.')

        self.is_sysadmin = authz.is_sysadmin(c.user)

        # Orgs of which the logged user is admin
        context = {'model': model, 'user': c.user or c.author}
        self.authz_orgs = p.toolkit.get_action('organization_list_for_user')(context, {})

        if not self.is_sysadmin and not self.authz_orgs:
            # User does not have permissions on any publisher
            p.toolkit.abort(401, 'Permission denied, only publisher administrators can manage CSV files.')

        if p.toolkit.request.method == 'GET':
            return p.toolkit.render('csv/upload.html')
        elif p.toolkit.request.method == 'POST':
            csv_file = p.toolkit.request.POST['file']
            if not hasattr(csv_file, 'filename'):
                p.toolkit.abort(400, 'No CSV file provided')
            vars = {}
            vars['file_name'] = csv_file.filename
            fieldnames = [f[0] for f in CSV_MAPPING]
            warnings = {}
            errors = {}
            data = csv_file.file.read()
            data = StringIO.StringIO(data)
            try:
                reader = csv.reader(data)
                columns = next(reader)

                missing_columns = [f for f in fieldnames if f not in columns and f not in OPTIONAL_COLUMNS]
                surplus_columns = [f for f in columns if f not in fieldnames]

                if len(surplus_columns):
                    warnings['1'] = {}
                    warnings['1']['file'] = 'Ignoring extra columns: %s' % ', '.join(sorted(surplus_columns))
                    warnings = {'Ignoring extra columns': '%s' % ', '.join(sorted(surplus_columns))}

                if len(missing_columns):
                    errors = {'Missing columns': '%s' % ', '.join(sorted(missing_columns))}
                    errors['1']['file'] = 'Ignoring extra columns: %s' % ', '.join(sorted(surplus_columns))

                if not len(errors.keys()):
                    json_data = []
                    for row in reader:
                        d = OrderedDict()
                        for i, x in enumerate(row):
                            d[columns[i]] = x
                        json_data.append(d)
                    ckan_ini_filepath = os.path.abspath(config['__file__'])
                    if not json_data:
                        p.toolkit.abort(400, 'No data found in CSV file.')
                    job = celery.send_task("iati.read_csv_file", args=[ckan_ini_filepath, json.dumps(json_data), c.user], task_id=str(uuid.uuid4()))
                    vars['task_id'] = job.task_id
                else:
                    p.toolkit.abort(400, ('Error in CSV file : {0}; {1}'.format(warnings, errors)))
            except Exception as e:
                vars['errors'] = errors
                vars['warnings'] = warnings
                p.toolkit.abort(400, ('Error opening CSV file: {0}'.format(e.message)))

            return p.toolkit.render('csv/result.html', extra_vars=vars)

    def check_status(self, task_id=None):
        result = {}
        if task_id:
            job = celery.AsyncResult(id=task_id)
            result.update({'status': job.state})
            if job.result:
                result['result'] = {}
                try:
                    data = json.loads(job.result)
                    result['result']['added'] = data['added']
                    result['result']['updated'] = data['updated']
                    result['result']['errors'] = data['errors']
                    result['result']['warnings'] = data['warnings']
                except Exception as e:
                    result.update({'status': "Error getting upload result"})
        else:
            result.update({'status': 'Invalid request.'})
        return json.dumps(result)

    def write_csv_file(self, publisher):
        context = {'model': model, 'user': c.user or c.author}
        try:
            if publisher == 'all':
                package_ids = p.toolkit.get_action('package_list')(context, {})
                packages = []
                for pkg_id in package_ids:
                    try:
                        package = p.toolkit.get_action('package_show')(context, {'id': pkg_id})
                        package.pop('state', None)
                        packages.append(package)
                    except p.toolkit.NotAuthorized:
                        log.warn('User %s not authorized to read package %s' % (c.user, pkg_id))
                        continue

            elif publisher == 'template':
                # Just return an empty CSV file with just the headers
                packages = []
            else:
                packages = get_packages_for_org(context, publisher)
        except p.toolkit.ObjectNotFound:
            p.toolkit.abort(404, 'Organization not found')

        f = StringIO.StringIO()

        output = ''
        try:
            fieldnames = [n[0] for n in CSV_MAPPING if n[0] != 'state']
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            headers = dict( (n[0],n[0]) for n in CSV_MAPPING if n[0] != 'state')
            writer.writerow(headers)

            packages.sort()
            for package in packages:
                if package:
                    row = {}
                    extras_dict = extras_to_dict(package)
                    for fieldname, entity, key in CSV_MAPPING:
                        if key == 'state':
                            continue
                        value = None
                        if entity == 'organization':
                            if len(package['organization']):
                                value = package['organization']['name']
                        elif entity == 'resources':
                            if len(package['resources']) and key in package['resources'][0]:
                                value = package['resources'][0][key]
                        else:
                            if key in package:
                                value = package[key]
                            elif key in extras_dict:
                                value = extras_dict[key]
                        row[fieldname] = value

                        for field_to_check in ('title', 'description'):
                            if fieldname == field_to_check and row.get(field_to_check):
                                row[field_to_check] = row[field_to_check].encode('utf-8')

                    writer.writerow(row)
            output = f.getvalue()
        finally:
            f.close()

        return output

def load_config(ckan_ini_filepath):
    import paste.deploy
    config_abs_path = os.path.abspath(ckan_ini_filepath)
    conf = paste.deploy.appconfig('config:' + config_abs_path)
    import ckan
    ckan.config.environment.load_environment(conf.global_conf,
                                             conf.local_conf)

    ## give routes enough information to run url_for
    parsed = urlparse.urlparse(conf.get('ckan.site_url', 'http://0.0.0.0'))
    request_config = routes.request_config()
    request_config.host = parsed.netloc + parsed.path
    request_config.protocol = parsed.scheme



def register_translator():
    # Register a translator in this thread so that
    # the _() functions in logic layer can work
    from paste.registry import Registry
    from pylons import translator
    from ckan.lib.cli import MockTranslator
    global registry
    registry = Registry()
    registry.prepare()
    global translator_obj
    translator_obj = MockTranslator()
    registry.register(translator, translator_obj)


@celery.task(name="iati.read_csv_file", serializer='json')
def read_csv_file(ckan_ini_filepath, csv_file, user):
    load_config(ckan_ini_filepath)
    register_translator()

    def get_package_dict_from_row(row, context):
        package = {}
        extras_dict = []

        for fieldname, entity, key in CSV_MAPPING:
            if fieldname in row:
                # If value is None (empty cell), property will be set to blank
                value = row[fieldname]

                if fieldname in ('recipient-country', ):
                    value = value.upper()

                if entity == 'organization':
                    package['owner_org'] = value
                elif entity == 'resources':
                    if 'resources' not in package:
                        package['resources'] = [{}]
                    package['resources'][0][key] = value
                elif entity == 'extras':
                    extras_dict.append({'key': key, 'value': value})
                else:
                    package[key] = value
        package['extras'] = extras_dict

        # Try to handle rogue Windows encodings properly
        for key in ('title', 'notes'):
            if package.get(key):
                try:
                    package[key] = package[key].decode('utf-8')
                except UnicodeDecodeError:
                    package[key] = _fix_unicode(package[key])

        # If no description provided, we assume delete it
        package['notes'] = package.get('notes', '')

        return package

    def create_or_update_package(package_dict, counts=None, context=None):
        context = {
            'model': model,
            'session': model.Session,
            'user': user,
        }
        # Check if package exists

        try:
            # Get rid of auth audit on the context otherwise we'll get an
            # exception
            context.pop('__auth_audit', None)

            existing_package_dict = p.toolkit.get_action('package_show')(context, {'id': package_dict['name']})
            # Update package
            log.info('Package with name "%s" exists and will be updated' % package_dict['name'])

            package_dict.update({'id': existing_package_dict['id']})

            package_dict['state'] = 'active'

            context['message'] = 'CSV import: update dataset %s' % package_dict['name']

            updated_package = p.toolkit.get_action('package_update')(context, package_dict)
            if counts:
                counts['updated'].append(updated_package['name'])
            log.debug('Package with name "%s" updated' % package_dict['name'])
        except p.toolkit.ObjectNotFound:
            # Package needs to be created
            log.info('Package with name "%s" does not exist and will be created' % package_dict['name'])

            package_dict.pop('id', None)

            context['message'] = 'CSV import: create dataset %s' % package_dict['name']
            # This is a work around for #1257. package_create auth function
            # looks for organization_id instead of owner_org.
            package_dict['organization_id'] = package_dict['owner_org']

            # Get rid of auth audit on the context otherwise we'll get an
            # exception
            context.pop('__auth_audit', None)

            new_package = p.toolkit.get_action('package_create')(context, package_dict)
            if counts:
                counts['added'].append(new_package['name'])
            log.debug('Package with name "%s" created' % package_dict['name'])

    fieldnames = [f[0] for f in CSV_MAPPING]
    warnings = {}
    errors = {}
    data = json.loads(csv_file)

    fields_from_csv = []
    for key in data[0].iterkeys():
        fields_from_csv.append(key)

    missing_columns = [f for f in fieldnames if f not in fields_from_csv and f not in OPTIONAL_COLUMNS]
    surplus_columns = [f for f in fields_from_csv if f not in fieldnames]

    if len(surplus_columns):
        warnings['1'] = {}
        warnings['1']['file'] = 'Ignoring extra columns: %s' % ', '.join(sorted(surplus_columns))

    if len(missing_columns):
        error = {'file': 'Missing columns: %s' % ', '.join(sorted(missing_columns))}
        return [], [], [], [('1', error)]

    context = {'model': model, 'session': model.Session, 'user': user, 'api_version': '1'}

    counts = {'added': [], 'updated': []}

    for i, row in enumerate(data):
        errors[i] = {}
        print row
        try:
            org = p.toolkit.get_action('organization_show')(context, {'id': row['registry-publisher-id']})
        except p.toolkit.ObjectNotFound:
            msg = 'Publisher not found: %s' % row['registry-publisher-id']
            log.error('Error in row %i: %s' % (i, msg))
            errors[i]['registry-publisher-id'] = [msg]
            continue

        try:
            try:
                package_dict = get_package_dict_from_row(row, context)
            except UnicodeDecodeError, e:
                msg = 'Encoding error, could not decode dataset title or description: {0}, {1}'.format(
                        row['title'], row['description'])
                log.error('Error in row %i: %s' % (i+1, msg))
                errors[i]['title'] = [msg]
                continue

            create_or_update_package(package_dict, counts, context=context)

            del errors[i]
        except p.toolkit.ValidationError, e:
            iati_keys = dict([(f[2], f[0]) for f in CSV_MAPPING])
            for key, msgs in e.error_dict.iteritems():
                iati_key = iati_keys.get(key, key)
                log.error('Error in row %i: %s: %s' % (
                    i+1, iati_key, str(msgs)))
                errors[i][iati_key] = msgs
        except p.toolkit.NotAuthorized, e:
            msg = 'Not authorized to publish to this organization: %s' % row['registry-publisher-id']
            log.error('Error in row %i: %s' % (i+1, msg))
            errors[i]['registry-publisher-id'] = [msg]
        except p.toolkit.ObjectNotFound, e:
            msg = 'Publisher not found: %s' % row['registry-publisher-id']
            log.error('Error in row %i: %s' % (i+1, msg))
            errors[i]['registry-publisher-id'] = [msg]

    warnings = sorted(warnings.iteritems())
    errors = sorted(errors.iteritems())
    counts['warnings'] = warnings
    counts['errors'] = errors

    return json.dumps(counts)

    def get_package_dict_from_row(self, row, context):
        package = {}
        extras_dict = []

        for fieldname, entity, key in CSV_MAPPING:
            if fieldname in row:
                # If value is None (empty cell), property will be set to blank
                value = row[fieldname]

                if fieldname in ('recipient-country', ):
                    value = value.upper()

                if entity == 'organization':
                    package['owner_org'] = value
                elif entity == 'resources':
                    if not 'resources' in package:
                       package['resources'] = [{}]
                    package['resources'][0][key] = value
                elif entity == 'extras':
                    extras_dict.append({'key': key, 'value': value})
                else:
                    package[key] = value
        package['extras'] = extras_dict

        # Try to handle rogue Windows encodings properly
        for key in ('title', 'notes'):
            if package.get(key):
                try:
                    package[key] = package[key].decode('utf-8')
                except UnicodeDecodeError:
                    package[key] = _fix_unicode(package[key])

        # If no description provided, we assume delete it
        package['notes'] = package.get('notes', '')

        return package

    def create_or_update_package(self, package_dict, counts = None, context = None):
        context = {
            'model': model,
            'session': model.Session,
            'user': c.user,
        }
        # Check if package exists

        try:
            # Get rid of auth audit on the context otherwise we'll get an
            # exception
            context.pop('__auth_audit', None)

            existing_package_dict = p.toolkit.get_action('package_show')(context, {'id': package_dict['name']})
            # Update package
            log.info('Package with name "%s" exists and will be updated' % package_dict['name'])

            package_dict.update({'id':existing_package_dict['id']})

            package_dict['state'] = 'active'

            context['message'] = 'CSV import: update dataset %s' % package_dict['name']

            updated_package = p.toolkit.get_action('package_update')(context, package_dict)
            if counts:
                counts['updated'].append(updated_package['name'])
            log.debug('Package with name "%s" updated' % package_dict['name'])
        except p.toolkit.ObjectNotFound:
            # Package needs to be created
            log.info('Package with name "%s" does not exist and will be created' % package_dict['name'])

            package_dict.pop('id', None)

            context['message'] = 'CSV import: create dataset %s' % package_dict['name']
            # This is a work around for #1257. package_create auth function
            # looks for organization_id instead of owner_org.
            package_dict['organization_id'] = package_dict['owner_org']

            # Get rid of auth audit on the context otherwise we'll get an
            # exception
            context.pop('__auth_audit', None)

            new_package = p.toolkit.get_action('package_create')(context, package_dict)
            if counts:
                counts['added'].append(new_package['name'])
            log.debug('Package with name "%s" created' % package_dict['name'])

def get_packages_for_org(context, org_name):
    rows = 100
    start = 0

    packages = []

    data_dict = {
        'q':'*:*',
        'fq': 'organization:' + org_name,
        'rows': rows,
        'start': start,
    }

    def do_query(context, data_dict):

        return p.toolkit.get_action('package_search')(context, data_dict)

    pending = True
    while pending:
        query = do_query(context, data_dict)
        if len(query['results']):
            packages.extend(query['results'])
            data_dict['start'] += rows
        else:
            pending = False

    return packages
