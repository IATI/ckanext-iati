import logging
import csv
import StringIO
import uuid
import json
from collections import OrderedDict
import os
import routes
import urlparse
import re
import datetime as dt
from ckan import model
import ckan.authz as authz
from ckan.lib.base import c
import ckan.plugins as p
from ckanext.iati.helpers import extras_to_dict
import ckan.lib.jobs as jobs
from dateutil.parser import parse as date_parse
import time

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


class FieldValidator:

    def __init__(self):
        pass

    def is_empty_field(self):
        pass

    def is_contains_unicode(self, text):
        guess = chardet.detect(text)
        if guess["confidence"] < min_confidence:
            raise True
        text = unicode(text, guess["encoding"])
        text = text.encode('utf-8')

        return text

    @staticmethod
    def compare_clean_fields(fieldnames, columns, OPTIONAL_COLUMNS):

        """ Checks if the mentioned names in csv is in required fields or sub string of the required fields
        and replace with required name in columns - this is to handle dirty text and unicode problem"""

        tot_col = fieldnames + OPTIONAL_COLUMNS

        for indx, field in enumerate(columns):
            for f in tot_col:
                if f in field:
                    columns[indx] = f

        return columns

    @staticmethod
    def is_mandatory_fields_missing(fieldnames, columns, OPTIONAL_COLUMNS):

        """ Checks for any mandatory missing columns and ignore extra columns """

        result = {}

        columns = FieldValidator.compare_clean_fields(fieldnames, columns, OPTIONAL_COLUMNS)

        missing_columns = [f for f in fieldnames if f not in columns and f not in OPTIONAL_COLUMNS]
        surplus_columns = [f for f in columns if f not in fieldnames]

        if len(surplus_columns):
            result['warnings'] = {'Ignoring extra columns': '%s' % ', '.join(sorted(surplus_columns))}
            result['errors'] = {}

        if len(missing_columns):
            result['errors'] = {'Missing columns': '%s' % ', '.join(sorted(missing_columns))}
            result['warnings'] = {}

        # Check for empty dictionary
        if not(bool(result)):
            result['errors'] = {}
            result['warnings'] = {}

        return result, columns

    @staticmethod
    def parse_error_if_object(error_object):
        """ This is to parse if the error message is dictionary object - this scenario occurs from URL validator"""
        error_list = []

        for element in error_object:
            if type(element) is dict:
                for key in element:
                    error_list.append(str(element[key]))
            else:
                error_list.append(str(element))

        return error_list

    @staticmethod
    def date_time_parser(datetime_object):
        """ Only consider if the datetime column is of type "%Y-%m-%d %H:%M:%S.%f" """

        if len(datetime_object.strip()) == 0:
            pass
        elif len(datetime_object.strip()) < 8:
            msg = "Not in acceptable format - format should be YYYY-MM-DD HH:MM:SS or YYYY-MM-DD or format csv column to date/time"
            raise ValueError(msg)

        date_time = date_parse(datetime_object)
        date_time.date()

        return datetime_object
    
    @staticmethod
    def publisher_id_validator(publisher_id):
        all_publishers = p.toolkit.get_action('group_list')({}, {})
        publisher_id = str(publisher_id).strip()

        if (publisher_id != "") and (publisher_id in all_publishers):
            msg = "pass"
            return True, msg
        else:
            if publisher_id == "":
                msg = "publisher id cannot be null"
            else:
                msg = "Unknown publisher id"

            return False, msg

    @staticmethod
    def check_upload_file_is_csv(filename):
        filename, file_extension = os.path.splitext(filename)
        if file_extension.lower() != ".csv":
            msg = "File is not a csv file. Please upload a valid csv file"
            is_csv = False
        else:
            msg = ''
            is_csv = True
        return is_csv, msg


field_validator = FieldValidator()


def _fix_unicode(text, min_confidence=0.5):
    import chardet
    guess = chardet.detect(text)

    if guess["confidence"] < min_confidence:
        return UnicodeDecodeError
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
            vars = {}
            vars['file_name'] = ""
            vars['Stat'] = "Permission denied, only publisher administrators can manage CSV files. Please login with proper credentials"
            return p.toolkit.render('csv/result.html', extra_vars=vars)
        try:
            self.is_sysadmin = authz.is_sysadmin(c.user)
            # Orgs of which the logged user is admin
            context = {'model': model, 'user': c.user or c.author}
            self.authz_orgs = p.toolkit.get_action('organization_list_for_user')(context, {})
        except Exception:
            p.toolkit.abort(401, 'Try to refresh your session.')

        if not self.is_sysadmin and not self.authz_orgs:
            # User does not have permissions on any publisher
            vars = {}
            vars['file_name'] = ""
            vars['Stat'] = "Permission denied, only publisher administrators can manage CSV files. Please login with proper credentials"
            p.toolkit.render('csv/result.html', extra_vars=vars)

        if p.toolkit.request.method == 'GET':
            return p.toolkit.render('csv/upload.html')
        elif p.toolkit.request.method == 'POST':
            csv_file = p.toolkit.request.POST['file']
            if not hasattr(csv_file, 'filename'):
                vars = {}
                vars['Stat'] = "No CSV file provided. Please upload a csv file."
                vars['file_name'] = ""
                return p.toolkit.render('csv/result.html', extra_vars=vars)
            vars = {}
            vars['file_name'] = csv_file.filename
            fieldnames = [f[0] for f in CSV_MAPPING]
            data = csv_file.file.read()
            data = StringIO.StringIO(data)
            try:
                reader = csv.reader(data)
                columns = next(reader)

                #missing_columns = [f for f in fieldnames if f not in columns and f not in OPTIONAL_COLUMNS]
                #surplus_columns = [f for f in columns if f not in fieldnames]

                #if len(surplus_columns):
                    #warnings = {'Ignoring extra columns': '%s' % ', '.join(sorted(surplus_columns))}

                #if len(missing_columns):
                    #errors = {'Missing columns': '%s' % ', '.join(sorted(missing_columns))}

                missing_val, columns = field_validator.is_mandatory_fields_missing(fieldnames, columns, OPTIONAL_COLUMNS)

                errors = missing_val['errors']
                warnings = missing_val['warnings']

                if not len(errors.keys()):
                    json_data = []
                    tasks = []

                    for row_no, row in enumerate(reader):
                        task = OrderedDict()

                        d = OrderedDict()
                        for i, x in enumerate(row):
                            try:
                                d[columns[i]] = x.encode('utf-8')
                            except UnicodeDecodeError, e:
                                task[u'status'] = "failed"
                                task[u'error'] = "Column: '{}' Cannot be decoded - contains special character"\
                                    .format(columns[i])

                        task[u'title'] = d['title'] or 'No Title'
                        if len(row) <= 12:
                            task[u'status'] = "failed"
                            if len(row) == 0:
                                task[u'error'] = "Empty line"
                            else:
                                task[u'error'] = "Incomplete line"
                            task[u'task_id'] = str(uuid.uuid4())
                        else:
                            task[u'task_id'] = str(uuid.uuid4()) #this is a random ID that will change with the job ID if it gets created
                            pub_id_validation, error_msg = field_validator.publisher_id_validator(d['registry-publisher-id'])
                            if pub_id_validation:
                                ckan_ini_filepath = os.path.abspath(config['__file__'])
                                json_data =[]
                                json_data.append(d)
                                try:
                                    job = jobs.enqueue(read_csv_file,
                                                       [ckan_ini_filepath,
                                                        json.dumps(json_data,
                                                                   ensure_ascii=False), c.user])
                                    time.sleep(0.05)
                                    task[u'task_id'] = str(job.id)
                                except Exception, e:
                                    task[u'status'] = "failed"
                                    task[u'error'] = "File Cannot be decoded - contains unknown character"

                            else:
                                task[u'status'] = "failed"
                                task[u'error'] = 'Invalid Publisher ID: '+error_msg

                        tasks.append(json.dumps(task))

                    vars['tasks'] = tasks
                else:
                    vars['errors'] = errors
                    vars['warnings'] = warnings
                    vars['tasks'] = []

                    is_csv, csv_msg = field_validator.check_upload_file_is_csv(str(vars['file_name']))
                    if is_csv:

                        vars['Stat'] = 'Error in CSV file: {0}; {1}'.format(re.sub("([\{\}'])+", "", str(warnings)),
                                                                            re.sub("([\{\}'])+", "", str(errors)))
                        return p.toolkit.render('csv/result.html', extra_vars=vars)
                    else:
                        vars['Stat'] = csv_msg

            except Exception as e:
                vars['errors'] = {}
                vars['warnings'] = {}
                vars['tasks'] = []
                vars['Stat'] = "Please make sure the csv file is clean, " \
                               "there should not be any special characters, bold letters etc."

                return p.toolkit.render('csv/result.html', extra_vars=vars)
                #p.toolkit.abort(400, ('Error opening CSV file: {0}'.format("Please make sure csv encoding is right!s")))

            return p.toolkit.render('csv/result.html', extra_vars=vars)

    def check_status(self, task_id=None):
        """ Checks status of all the assigned background jobs csv upload functionality """
        result = {}

        if task_id and task_id != 'undefined':
            try:
                job = jobs.job_from_id(id=task_id)
                result.update({'status': job.get_status()})
                log.info(" csv check status info - job id: {}".format(task_id))
                log.info(" csv check status info - job status: {}".format(job.get_status()))

                if job.result:
                    result['result'] = {}
                    try:
                        data = json.loads(job.result)
                        result['result']['added'] = data['added']
                        result['result']['updated'] = data['updated']
                        result['result']['errors'] = data['errors']
                        result['result']['warnings'] = data['warnings']
                    except Exception as e:
                        result.update({'status': "failed"})
                        result['result']['errors'] = "Something went wrong, while checking the job status."
                        #print job.traceback
            except Exception as e:
                log.error("CSV Upload 1 check status error ********** {}".format(str(e)))
                result.update({'status': "failed"})
                result['result'] = {}
                result['result']['errors'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""

        else:
            log.error("CSV Upload check status 2 error ********** No task id")
            result.update({'status': 'failed'})
            result['result'] = {}
            result['result']['errors'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""

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
                    package[key] = package[key].encode('utf-8')
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

    #missing_columns = [f for f in fieldnames if f not in fields_from_csv and f not in OPTIONAL_COLUMNS]
    surplus_columns = [f for f in fields_from_csv if f not in fieldnames]

    if len(surplus_columns):
        warnings['1'] = {}
        warnings['1']['file'] = 'Ignoring extra columns: %s' % ', '.join(sorted(surplus_columns))

    #if len(missing_columns):
    #    error = {'file': 'Missing columns: %s' % ', '.join(sorted(missing_columns))}
    #    return [], [], [], [('1', error)]

    context = {'model': model, 'session': model.Session, 'user': user, 'api_version': '3'}

    counts = {'added': [], 'updated': []}

    for i, row in enumerate(data):
        errors[i] = {}

        try:
            # Check if publisher id exists.
            org = p.toolkit.get_action('organization_show')(context, {'id': row['registry-publisher-id']})
        except p.toolkit.ObjectNotFound:
            msg = 'Publisher not found: %s' % row['registry-publisher-id']
            log.error('Error in row %i: %s' % (i, msg))
            errors[i]['registry-publisher-id'] = [msg]
            continue

        try:
            try:
                package_dict = get_package_dict_from_row(row, context)

                try:
                    package_dict['data_updated'] = field_validator.date_time_parser(str(package_dict['data_updated']))
                except Exception, e:
                    msg = str("Not in acceptable format - format should be YYYY-MM-DD HH:MM:SS or YYYY-MM-DD or format csv column to date/time")
                    raise ValueError(msg)

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
                if iati_key == "name_or_id":
                    iati_key = 'registry-file-id'
                log.error('Error in row %i: %s: %s' % (
                    i+1, iati_key, str(msgs)))
                errors[i][iati_key] = FieldValidator.parse_error_if_object(msgs)
        except p.toolkit.NotAuthorized, e:
            msg = 'Not authorized to publish to this organization: %s' % row['registry-publisher-id']
            log.error('Error in row %i: %s' % (i+1, msg))
            errors[i]['registry-publisher-id'] = [msg]
        except p.toolkit.ObjectNotFound, e:
            msg = 'Publisher not found: %s' % row['registry-publisher-id']
            log.error('Error in row %i: %s' % (i+1, msg))
            errors[i]['registry-publisher-id'] = [msg]
        except ValueError, e:
            log.error('Error in row %i: %s' % (i + 1, str(e)))
            errors[i]['last-updated-datetime'] = [str(e)]

    warnings = sorted(warnings.iteritems())
    errors = sorted(errors.iteritems())

    counts['warnings'] = warnings
    counts['errors'] = errors

    return json.dumps(counts)


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

