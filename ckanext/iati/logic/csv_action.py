from flask import make_response
from ckan.common import config, c
import ckan.plugins as p
import ckan.model as model
import ckan.authz as authz
import ckan.logic as logic
import ckan.lib.jobs as jobs
from ckanext.iati.helpers import extras_to_dict, parse_error_object_to_list
from ckanext.iati import helpers as h
from ckanext.iati.logic import action
import sqlalchemy
import csv
import io
from collections import OrderedDict
import json
from xlwt import Workbook
import io
import datetime as dt
import os, codecs
import logging
import six
log = logging.getLogger(__name__)

_and_ = sqlalchemy.and_
_not_empty = p.toolkit.get_validator('not_empty')
_ignore_empty = p.toolkit.get_validator('ignore_empty')
_ignore_missing = p.toolkit.get_validator('ignore_missing')
_int_validator = p.toolkit.get_validator('int_validator')
ValidationError = logic.ValidationError


class FormatError(Exception):
    pass


class PublishersListDownload:

    def __init__(self, download_format, request_recent_publisher=False):
        self.request_type_recent_publisher = request_recent_publisher
        self.download_format = self._get_format(download_format)
        self._site_url = config.get('ckan.site_url')
        self._datasets_link = self._site_url + "/publisher/{}"

        self._func_mapping = {
                              'extras_publisher_organization_type':h.get_organization_type_title,
                              'extras_publisher_country':h.get_country_title
                            }
        self._set_mapping()

    def _set_mapping(self):
        """
        Set csv column headers accoring to the request type.
        If the request is from recent publishers )only for sysadmins), we need first_published_date column
        :return:
        """
        self._headers = ['Publisher', 'IATI Organisation Identifier', 'Organization Type',
                         'HQ Country or Region', 'Datasets Count', 'Datasets Link']
        self._mapping = ['display_name', 'extras_publisher_iati_id', 'extras_publisher_organization_type',
                         'extras_publisher_country', 'package_count']

        if self.request_type_recent_publisher:
            self._headers.insert(4, "First Published Date")
            self._mapping.insert(4, "extras_publisher_first_publish_date")

        self._headers = tuple(self._headers)
        self._mapping = tuple(self._mapping)

    def _get_xml_value(self, val):
        val_str = str(val, 'utf-8') if isinstance(val, bytes) else val
        val_str = val_str.replace('&', "&amp;")
        return val_str

    def _get_xml_name(self, val):
        val = val.lower()
        return val.replace(" ", '-')

    def _get_format(self, download_format):

        try:
            download_format = download_format.lower()
            _formats = ('csv', 'json', 'xml', 'xls')
            if download_format not in _formats:
                raise FormatError
            return download_format
        except Exception as e:
            raise FormatError(e)

    @staticmethod
    def _get_publisher_data():
        """
        We cannot use API organization_list with all_fields=True, because it will be expensive process
        to by pass max limits
        :return: dict
        """
        # TODO: Need optimization
        # First get package count and then join with Group with ownr_org
        package_count = model.Session.query(model.Group, model.Package.owner_org,
                                            sqlalchemy.func.count(model.Package.id).label('package_count')).join(
            model.Package, model.Group.id == model.Package.owner_org).filter(
            _and_(
                model.Group.is_organization == True, model.Group.state == 'active',
                model.Package.private == False, model.Package.state == 'active'
            )
        ).group_by(model.Group.id, model.Package.owner_org).subquery()

        organization = model.Session.query(model.Group, package_count.c.package_count).join(
            package_count, model.Group.id == package_count.c.id).join(model.GroupExtra)

        log.info(organization.as_scalar())

        return organization.all()

    def _prepare(self, data):
        """
        Prepare the data for download
        :param data:
        :return:
        """
        clean_data = []
        extras = dict(data.Group._extras)
        for key in self._mapping[:-1]:
            val = ''
            if hasattr(data.Group, key):
                val = getattr(data.Group, key)

            if "extras_" in key:
                val = extras.get(key.replace("extras_", ''), '')
                if val:
                    val = val.value

                if key in self._func_mapping:
                    val = self._func_mapping.get(key)(val)

            clean_data.append(val)
        clean_data.append(data.package_count)
        clean_data.append(self._datasets_link.format(data.Group.name))
        return clean_data

    def csv(self):
        """
        CSV download.

        Sysadmin recent publisher is allowed to download only csv
        :return:
        """
        f = io.StringIO()
        writer = csv.writer(f)
        writer.writerow(list(self._headers))
        _org_data = PublishersListDownload._get_publisher_data()
        rows = []
        for org in _org_data:
            if org.Group.state == 'active' and int(org.package_count) > 0:
                org_data = self._prepare(org)
                if self.request_type_recent_publisher:
                    rows.append(org_data)
                else:
                    writer.writerow([s if six.PY2 and isinstance(s, str) else s for s in org_data])

        # This is expensive but we need sorting for first published
        # date since its hard to get sorted for GroupExtra table
        if self.request_type_recent_publisher:
            rows = sorted(rows, key=lambda entry: entry[4], reverse=True)
            for csv_row in rows:
                writer.writerow([s if six.PY2 and isinstance(s, str) else s for s in csv_row])

        output = f.getvalue()
        f.close()
        response = make_response(output)
        response.headers['Content-type'] = 'text/csv'
        return response

    def json(self):
        """
        Json download
        :return:
        """
        f = io.StringIO()
        json_data = []

        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
            if org.Group.state == 'active' and int(org.package_count) > 0:
                ordered_dict = OrderedDict(zip(self._headers, self._prepare(org)))
                for key, value in ordered_dict.items():
                    if isinstance(value, bytes):
                        ordered_dict[key] = value.decode('utf-8')

                json_data.append(ordered_dict)

        json.dump(json_data, f)
        output = f.getvalue()
        f.close()
        response = make_response(output)
        response.headers['Content-type'] = 'application/json'
        return response

    def xml(self):
        """
        xml format download
        :return:
        """
        f = io.StringIO()

        fields = list(self._headers)
        fields.pop(1)

        xml = ['<?xml version="1.0" encoding="UTF-8" ?>']
        _observations = '   <{}>{}</{}>'
        xml.append('<iati-publishers-list>')

        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
            if org.Group.state == 'active' and int(org.package_count) > 0:
                _dt = self._prepare(org)
                _dt[4] = str(int(_dt[4])) # Package count to string
                _iati_identifier = _dt.pop(1)
                xml.append('<iati-identifier id="{}">'.format(_iati_identifier))
                for _index, _field in enumerate(fields):
                    field = self._get_xml_name(_field)
                    if field == "Datasets Link":
                        xml.append('<iati-publisher-page xmlns:xlink="http://www.w3.org/1999/xlink">')
                        xml.append('    <iati-publisher-page xlink:type="simple" '
                                   'xlink:href="{}">{}</iati-publisher-page>'.format(_dt[_index],
                                                                                     self._get_xml_value(_dt[0])))
                        xml.append('</iati-publisher-page>')
                    else:
                        xml.append(_observations.format(field, self._get_xml_value(_dt[_index]), field))
                xml.append('</iati-identifier>')

        xml.append('</iati-publishers-list>')

        f.write("\n".join(xml))
        output = f.getvalue()
        f.close()
        response = make_response(output)
        response.headers['Content-type'] = 'text/xml'
        return response

    def xls(self):
        """
        xls format download
        :return:
        """
        f = io.BytesIO()
        wb = Workbook(encoding='utf-8')
        sheet1 = wb.add_sheet('IATI Publishers List')
        _org_data = PublishersListDownload._get_publisher_data()

        # Write Headers
        for _index, _field in enumerate(self._headers):
            sheet1.write(0, _index, _field)

        # Write Rows and Values
        _row = 1
        for org in _org_data:
            if org.Group.state == 'active' and int(org.package_count) > 0:
                _dt = self._prepare(org)
                # Write Items
                for _col, _item in enumerate(_dt):
                    if isinstance(_item, bytes):
                        _item = _item.decode('utf-8')
                    sheet1.write(_row, _col, _item)
                _row += 1

        wb.save(f)
        output = f.getvalue()
        f.close()
        response = make_response(output)
        return response

    def download(self):

        response = getattr(PublishersListDownload, self.download_format)(self)
        file_name = 'iati_publishers_list'
        response.headers['Content-disposition'] = 'attachment;filename={}.{}'.format(file_name,
                                                                                     self.download_format)
        return response


class PublisherRecordsDownload:

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

    MAX_ROWS = int(config.get('ckanext.iati.max_rows_csv_upload', 100))

    def __init__(self):
        pass

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

    def write_to_csv(self, publisher):
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

            f = io.StringIO()
            fieldnames = [n[0] for n in self.CSV_MAPPING if n[0] != 'state']
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            headers = {n[0]: n[0] for n in self.CSV_MAPPING if n[0] != 'state'}
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

                    writer.writerow(row)
            output = f.getvalue()
            f.close()
            return output
        except p.toolkit.ObjectNotFound:
            p.toolkit.abort(404, 'Organization not found')


class PublisherRecordsUpload(PublisherRecordsDownload):

    def __init__(self, *args, **kwargs):
        PublisherRecordsDownload.__init__(self)

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
        bom_length = len(codecs.BOM_UTF8)
        data = csv_file.read()
        if data.startswith(codecs.BOM_UTF8):
            data = data[bom_length:]

        if not data:
            raise ValidationError("CSV file is empty")

        decoded_data = data.decode('utf-8')
        buffer = io.StringIO(decoded_data)
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
                raise ValidationError("Mandatory/unrecognized CSV columns. Given csv fields: {}")

        # Validate no of rows
        row_count = sum(1 for _ in reader)
        log.info("Number of rows in csv: {}".format(str(row_count)))
        if row_count > self.MAX_ROWS:
            raise ValidationError(
                "Exceeded the limit. Maximum allowed rows is {0}".format(self.MAX_ROWS)
            )

        return data
