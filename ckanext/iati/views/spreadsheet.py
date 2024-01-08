from flask import Blueprint, make_response
from ckan.lib.base import render, abort
from ckan.common import _, c, g, config, request
from ckan import model
from ckan import logic
import ckan.lib.jobs as jobs
import ckan.plugins as p
import ckan.lib.helpers as h
from ckan.views import group as core_group_view
from ckanext.iati.logic.csv_action import PublisherRecordsUpload, PublisherRecordsDownload
from ckanext.iati import helpers as iati_h
from collections import OrderedDict
import json
import io
import csv
import uuid
import datetime as dt
import logging

log = logging.getLogger(__name__)

NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized
ValidationError = logic.ValidationError


def records_upload_process(row_dict, user):
    """

    :param row_dict:
    :param user:
    :return:
    """

    def _prepare_package_dict_from_row(row, context):
        """

        :param row:
        :param context:
        :return:
        """
        package = dict()
        extras_dict = []
        for fieldname, entity, key in PublisherRecordsUpload.CSV_MAPPING:
            if fieldname in row:
                # If value is None (empty cell), property will be set to blank
                value = row[fieldname]

                if fieldname in ('recipient-country',):
                    value = value.upper()

                if entity == 'organization':
                    package['owner_org'] = value
                elif entity == 'resources':
                    if entity not in package:
                        package[entity] = [{}]
                    package[entity][0][key] = value
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
            context.pop('__auth_audit', None)  # Get rid of auth audit context from package show
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
            context.pop('__auth_audit', None)  # Get rid of auth audit context from package show

            _created_package = p.toolkit.get_action('package_create')(context, package_dict)
            log.debug('Package with name "%s" created' % package_dict['name'])
            status['created'] = _created_package['name']

        return status

    def read_csv_file(csv_file, user):
        """
        Read the uploaded csv file to upload records to publishers
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
            except p.toolkit.ValidationError as e:
                iati_keys = dict([(f[2], f[0]) for f in PublisherRecordsUpload.CSV_MAPPING])
                for key, msgs in e.error_dict.items():
                    iati_key = iati_keys.get(key, key)
                    if iati_key == "name_or_id":
                        iati_key = 'registry-file-id'
                    log.error('Error in row %i: %s: %s' % (
                        i + 1, iati_key, str(msgs)))
                    errors[i][iati_key] = iati_h.parse_error_object_to_list(msgs)
            except p.toolkit.NotAuthorized as e:
                msg = 'Not authorized to publish to this organization: %s' % row['registry-publisher-id']
                log.error('Error in row %i: %s' % (i + 1, msg))
                errors[i]['registry-publisher-id'] = [msg]
            except p.toolkit.ObjectNotFound as e:
                msg = 'Publisher not found: %s' % row['registry-publisher-id']
                log.error('Error in row %i: %s' % (i + 1, msg))
                errors[i]['registry-publisher-id'] = [msg]
            except ValueError as e:
                log.error('Error in row %i: %s' % (i + 1, str(e)))
                errors[i]['last-updated-datetime'] = [str(e)]

        warnings = sorted(warnings.items())
        errors = sorted(errors.items())

        counts['warnings'] = warnings
        counts['errors'] = errors

        return json.dumps(counts)

    return read_csv_file(row_dict, user)


spreadsheet = Blueprint('spreadsheet', __name__, url_prefix='/csv')


def index():
    is_organization = True
    group_type = 'organization'
    return core_group_view.index(group_type, is_organization)


def download_publisher_records(id):

    context = {'model': model, 'user': c.user or c.author}

    csv_writer = PublisherRecordsDownload()
    # all publishers download is not recommended
    # Because publishers list is huge and not recommended to download from API's

    if id not in ('template', ):
        try:
            _ = p.toolkit.get_action('organization_show')(context, {'id': id})
            output = csv_writer.write_to_csv(id)
        except p.toolkit.ObjectNotFound:
            p.toolkit.abort(404, 'Publisher not found')
    else:
        output = csv_writer.write_to_csv(id)

    response = make_response(output)
    file_name = id if id else 'iati-registry-records'
    response.headers['Content-type'] = 'text/csv'
    response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % str(file_name)

    return response


def csv_upload_datasets():

    self = PublisherRecordsUpload()
    unauthorized = self._validate_users()
    if unauthorized:
        return unauthorized

    if request.method == "GET":
        return render('csv/upload.html')
    else:
        vars = dict()
        csv_file = request.files['file']

        try:
            _data = self._validate_csv_files(csv_file)
        except ValidationError as e:
            h.flash_error(_(e.error_dict['message']))
            return h.redirect_to('spreadsheet.csv_upload_datasets')

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

            task['title'] = "No Title" if not row_dict.get('title', '') else row_dict.get('title')
            task['task_id'] = str(uuid.uuid4())
            job = jobs.enqueue(records_upload_process,
                               [json.dumps([row_dict], ensure_ascii=False).encode('utf-8'), c.user])
            task['task_id'] = str(job.id)
            tasks.append(json.dumps(task))

        vars['tasks'] = tasks

        return render('csv/result.html', extra_vars=vars)


def publishers_upload_status(task_id):
    """
    Check status for the csv upload
    :param task_id:
    :return:
    """
    result = {}
    job = jobs.job_from_id(id=task_id)

    if not job:
        raise ValidationError("No job associated with the given task id")
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

    return json.dumps(result)


spreadsheet.add_url_rule('/download', view_func=index)
spreadsheet.add_url_rule('/download/<id>', view_func=download_publisher_records)
spreadsheet.add_url_rule('/upload', view_func=csv_upload_datasets, methods=['GET', 'POST'])
spreadsheet.add_url_rule('/check_status/<task_id>', view_func=publishers_upload_status, methods=['GET'])
