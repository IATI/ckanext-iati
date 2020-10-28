import csv
import StringIO
from collections import OrderedDict
import json
from xlwt import Workbook
from ckanext.iati import helpers as h
from ckanext.iati.logic import action
from ckan.common import config, c
import ckan.plugins as p
import ckan.model as model
import sqlalchemy
import logging
log = logging.getLogger(__name__)

_and_ = sqlalchemy.and_


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
        val = val.replace('&', "&amp;")
        return val

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
                val = getattr(data.Group, key).encode('utf-8')

            if "extras_" in key:
                val = extras.get(key.replace("extras_", ''), '')
                if val:
                    val = val.value.encode('utf-8')

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
        f = StringIO.StringIO()
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
                    writer.writerow(org_data)

        # This is expensive but we need sorting for first published
        # date since its hard to get sorted for GroupExtra table
        if self.request_type_recent_publisher:
            rows = sorted(rows, key=lambda entry: entry[4], reverse=True)
            for csv_row in rows:
                writer.writerow(csv_row)

        output = f.getvalue()
        f.close()
        p.toolkit.response.headers['Content-type'] = 'text/csv'
        return output

    def json(self):
        """
        Json download
        :return:
        """
        f = StringIO.StringIO()
        json_data = []

        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
            if org.Group.state == 'active' and int(org.package_count) > 0:
                json_data.append(OrderedDict(zip(self._headers, self._prepare(org))))

        json.dump(json_data, f)
        output = f.getvalue()
        f.close()
        p.toolkit.response.headers['Content-type'] = 'application/json'
        return output

    def xml(self):
        """
        xml format download
        :return:
        """
        f = StringIO.StringIO()

        fields = list(self._headers)
        fields.pop(1)

        xml = ['<?xml version="1.0" encoding="UTF-8" ?>']
        _observations = '   <{}>{}</{}>'
        xml.append('<iati-publishers-list>')

        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
            if org.Group.state == 'active' and int(org.package_count) > 0:
                _dt = self._prepare(org)
                _iati_identifier = _dt.pop(1)
                xml.append('<iati-identifier id="{}">'.format(_iati_identifier))
                for _index, _field in enumerate(fields):
                    field = self._get_xml_name(_field)
                    if field == "datasets-link":
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
        p.toolkit.response.headers['Content-type'] = 'text/xml'

        return output

    def xls(self):
        """
        xls format download
        :return:
        """
        f = StringIO.StringIO()
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
                    sheet1.write(_row, _col, _item)
                _row += 1

        wb.save(f)
        output = f.getvalue()
        f.close()
        return output

    def download(self):

        op = getattr(PublishersListDownload, self.download_format)(self)
        file_name = 'iati_publishers_list'
        p.toolkit.response.headers['Content-disposition'] = 'attachment;filename={}.{}'.format(file_name,
                                                                                               self.download_format)
        return op

