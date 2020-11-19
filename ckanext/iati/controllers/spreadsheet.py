from ckan import model
import ckan.lib.helpers as h
import ckan.logic as logic
import ckan.authz as authz
from ckan.common import _, c
import ckan.plugins as p
from ckanext.iati.helpers import extras_to_dict, parse_error_object_to_list
import ckan.lib.jobs as jobs
from dateutil.parser import parse as date_parse
from ckanext.iati.controllers.publisher_list_download import PublishersListDownload
from ckan.common import config
import logging
import time
import csv
import io
import uuid
import json
from collections import OrderedDict
import os
import routes
import urlparse
import re
import datetime as dt

log = logging.getLogger(__name__)
_not_empty = p.toolkit.get_validator('not_empty')
_ignore_empty = p.toolkit.get_validator('ignore_empty')
_ignore_missing = p.toolkit.get_validator('ignore_missing')
_int_validator = p.toolkit.get_validator('int_validator')
ValidationError = logic.ValidationError


class CSVController(p.toolkit.BaseController):

    CSV_MAPPING = [
        ('registry-publisher-id', 'organization', 'name'),
        ('registry-file-id', 'package', 'name'),
        ('title', 'package', 'title'),
        ('description', 'package', 'notes'),
        ('contact-email', 'package', 'author_email'),
        ('state', 'package', 'state'),
        ('source-url', 'resources', 'url'),
        ('file-type', 'package', 'filetype'),
        ('recipient-country', 'package', 'country'),
        ('default-language', 'package', 'language'),
        ('secondary-publisher', 'package', 'secondary_publisher'),
    ]

    OPTIONAL_COLUMNS = ['state', 'description', 'default-language', 'secondary-publisher']

    MAX_ROWS = int(config.get('ckanext.iati.max_rows_csv_upload', 101))

    def _validate_users(self):
        """
        Validate user access -
        :return: None
        """
        log.info("Validating the logged in user")
        if not c.user:
            return p.toolkit.abort(401, 'You are not logged. Please login')

        self.is_sysadmin = authz.is_sysadmin(c.user)
        context = {'model': model, 'user': c.user or c.author}
        self.authz_orgs = p.toolkit.get_action('organization_list_for_user')(context, {})

        if not self.is_sysadmin and not self.authz_orgs:
            return p.toolkit.abort(403, 'You are not authorized. You are not an admin of any publisher.')

        return None

    def _validate_csv_files(self, csv_file):
        """
        Validate uploaded csv files.
        :return:
        """
        log.info("Validating the uploaded csv files")

        if not hasattr(csv_file, 'filename'):
            raise ValidationError("No CSV file provided. Please upload a CSV file.")

        # Verify csv file extension
        if os.path.splitext(csv_file.filename)[-1].lower() != '.csv':
            raise ValidationError(
                "Uploaded file is not a csv file. Please upload a csv file"
            )

        # Validate csv columns
        # Validate Mandatory fields.

        data = csv_file.file.read()

        if not data:
            raise ValidationError("CSV file is empty")

        buffer = io.BytesIO(data)
        log.info("Validating CSV file....")
        reader = csv.reader(buffer)
        columns = next(reader)

        # Validate columns
        if not columns:
            buffer.close()
            raise ValidationError("Mandatory fields are missing. "
                                  "Download csv upload template (verify mandatory columns) and "
                                  "upload the file accordingly.")

        for _col in self.CSV_MAPPING:
            is_optional = _col[0] in self.OPTIONAL_COLUMNS
            in_columns = _col[0] in columns
            if not is_optional and not in_columns:
                buffer.close()
                raise ValidationError("Mandatory fields are missing. "
                                      "Download csv upload template (verify mandatory columns) and "
                                      "upload the file accordingly.")

        # Validate no of rows
        row_count = sum(1 for _ in reader)
        log.info("Number of rows in csv: {}".format(str(row_count)))
        if row_count > self.MAX_ROWS:
            raise ValidationError(
                "Exceeded the limit. Maximum allowed rows is 50"
            )

        return data

    def _get_packages_for_org(self, context, org_name):
        """

        :param context:
        :param org_name:
        :return:
        """
        rows = 100
        start = 0

        packages = []

        data_dict = {
            'q': '*:*',
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

    def _write_csv_file(self, publisher):
        """

        :param publisher:
        :return:
        """
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
                packages = self._get_packages_for_org(context, publisher)

            f = io.BytesIO()
            fieldnames = [n[0] for n in self.CSV_MAPPING if n[0] != 'state']
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            headers = dict((n[0], n[0]) for n in self.CSV_MAPPING if n[0] != 'state')
            writer.writerow(headers)

            for package in packages:
                if package:
                    row = {}
                    extras_dict = extras_to_dict(package)
                    for fieldname, entity, key in self.CSV_MAPPING:
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
            f.close()
            return output
        except p.toolkit.ObjectNotFound:
            p.toolkit.abort(404, 'Organization not found')

    def download(self, publisher):
        """

        :param publisher:
        :return:
        """
        context = {'model': model, 'user': c.user or c.author}

        if publisher and publisher not in ['all', 'template']:
            try:
                p.toolkit.get_action('organization_show')(context, {'id': publisher})
                output = self._write_csv_file(publisher)
                file_name = publisher if publisher else 'iati-registry-records'
                p.toolkit.response.headers['Content-type'] = 'text/csv'
                p.toolkit.response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % str(file_name)
                return output
            except p.toolkit.ObjectNotFound:
                p.toolkit.abort(404, 'Publisher not found')

        p.toolkit.abort(404, 'Publisher not found')

    def upload(self):
        """
        Upload csv functionality. GET and POST Methods
        :return:
        """

        unauthorized = self._validate_users()

        if unauthorized:
            return unauthorized

        if p.toolkit.request.method == 'GET':
            return p.toolkit.render('csv/upload.html')

        elif p.toolkit.request.method == 'POST':
            vars = dict()
            csv_file = p.toolkit.request.POST['file']

            try:
                _data = self._validate_csv_files(csv_file)
            except ValidationError as e:
                h.flash_error(_(e.error_dict['message']))
                return h.redirect_to('csv_upload')

            vars['file_name'] = csv_file.filename
            data = io.BytesIO(_data)
            log.info("Reading CSV file for upload....")
            reader = csv.reader(data)
            columns = next(reader)
            tasks = list()

            for row_no, row in enumerate(reader):
                task = OrderedDict()
                row_dict = OrderedDict()

                # try catch block for each row.
                for i, x in enumerate(row):
                    row_dict[columns[i].encode('utf-8')] = x.encode('utf-8')

                task[u'title'] = "No Title" if not row_dict.get('title', '') else row_dict.get('title')
                task[u'task_id'] = str(uuid.uuid4())
                job = jobs.enqueue(read_csv_file,
                                   [json.dumps([row_dict], ensure_ascii=False).encode('utf-8'), c.user])
                task[u'task_id'] = str(job.id)
                tasks.append(json.dumps(task))

            vars['tasks'] = tasks

            return p.toolkit.render('csv/result.html', extra_vars=vars)

    def check_status(self, task_id=None):
        """
        Check status for the csv upload
        :param task_id:
        :return:
        """
        result = {}
        if task_id and task_id != 'undefined':
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
        else:
            log.error("CSV Upload check status error no task id")
            result.update({'status': 'failed'})
            result['result'] = {}
            result['result'][
                'errors'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""

        return json.dumps(result)

    def publisher_list_download(self, download_format):
        pub_list = PublishersListDownload(download_format)
        return pub_list.download()


def _prepare_package_dict_from_row(row, context):
    """

    :param row:
    :param context:
    :return:
    """
    package = {}
    extras_dict = []

    for fieldname, entity, key in CSVController.CSV_MAPPING:
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
    package['resources'][0]['format'] = 'IATI-XML'
    return package


def _create_or_update_package(package_dict, user):
    """

    :param package_dict:
    :param user:
    :return:
    """
    context = {
        'model': model,
        'session': model.Session,
        'user': user,
        'disable_archiver': True,
        'api_version': '3'
    }
    status = dict()
    # Check if package exists
    try:
	# Try package update
        existing_package_dict = p.toolkit.get_action('package_show')(context, {'id': package_dict['name']})
        context.pop('__auth_audit', None) # Get rid of auth audit context from package show
        log.info('Package with name "%s" exists and will be updated' % package_dict['name'])
        package_dict.update({'id': existing_package_dict['id']})
        package_dict['state'] = 'active'
        context['message'] = 'CSV import: update dataset %s' % package_dict['name']
        
	_updated_package = p.toolkit.get_action('package_update')(context, package_dict)
        status['updated'] = _updated_package['name']
        # This indicates package update is successful
        log.debug('Package with name "%s" updated' % package_dict['name'])
    except p.toolkit.ObjectNotFound:
        # Package needs to be created
        log.info('Package with name "%s" does not exist and will be created' % package_dict['name'])
        package_dict.pop('id', None)
        context['message'] = 'CSV import: create dataset %s' % package_dict['name']
        package_dict['organization_id'] = package_dict['owner_org']
        context.pop('__auth_audit', None) # Get rid of auth audit context from package show
        
	_created_package = p.toolkit.get_action('package_create')(context, package_dict)
        log.debug('Package with name "%s" created' % package_dict['name'])
        status['created'] = _created_package['name']

    return status


def read_csv_file(csv_file, user):
    """

    :param csv_file:
    :param user:
    :return:
    """
    warnings = {}
    errors = {}
    data = json.loads(csv_file)
    context = {
        'model': model,
        'session': model.Session,
        'user': user,
        'api_version': '3'
    }

    counts = {
        'added': [],
        'updated': []
    }

    for i, row in enumerate(data):
        errors[i] = {}
        try:
            package_dict = _prepare_package_dict_from_row(row, context)
            package_dict['data_updated'] = str(dt.datetime.now())
            _status = _create_or_update_package(package_dict, user)
            if 'created' in _status:
                counts['added'].append(_status['created'])
            else:
                counts['updated'].append(_status['updated'])
        except p.toolkit.ValidationError, e:
            iati_keys = dict([(f[2], f[0]) for f in CSVController.CSV_MAPPING])
            for key, msgs in e.error_dict.iteritems():
                iati_key = iati_keys.get(key, key)
                if iati_key == "name_or_id":
                    iati_key = 'registry-file-id'
                log.error('Error in row %i: %s: %s' % (
                    i+1, iati_key, str(msgs)))
                errors[i][iati_key] = parse_error_object_to_list(msgs)
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
