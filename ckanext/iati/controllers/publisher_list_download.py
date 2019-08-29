from ckanext.iati import helpers as h
from ckan.common import config
import ckan.plugins as p
import csv
import StringIO
from collections import OrderedDict
import json
from xlwt import Workbook


class FormatError(Exception):
    pass


class PublishersListDownload:

    def __init__(self, download_format):
        self.download_format = self._get_format(download_format)
        self._headers = ('Publisher', 'IATI Organisation Identifier', 'Organization Type',
                         'HQ Country or Region', 'Datasets Count', 'Datasets Link')
        self._site_url = config.get('ckan.site_url')
        self._datasets_link = self._site_url + "/publisher/{}"
        self._mapping = ('display_name', 'extras_publisher_iati_id', 'extras_publisher_organization_type',
                         'extras_publisher_country', 'package_count')

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
            return download_format.lower()
        except Exception as e:
            raise FormatError(e)

    @staticmethod
    def _get_publisher_data():

        return h.organization_list_publisher_page()

    def _prepare(self, data, include_name=False):

        clean_data = []

        for field in self._mapping:
            if 'extras' in field:
                val = ''
                for _extra in data['extras']:
                    if _extra['key'] == field.replace("extras_", ''):
                        val = _extra['value']
                        break
                clean_data.append(val.encode('utf-8'))
            elif field == 'package_count':
                clean_data.append(str(data.get(field, '')))
            else:
                clean_data.append(data.get(field, '').encode('utf-8'))

        clean_data.append(self._datasets_link.format(data.get('name')))

        if include_name:
            clean_data.append(data.get('name'))
        return clean_data

    def csv(self):
        f = StringIO.StringIO()
        writer = csv.writer(f)
        writer.writerow(list(self._headers))
        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
            writer.writerow(self._prepare(org))

        output = f.getvalue()
        f.close()
        p.toolkit.response.headers['Content-type'] = 'text/csv'
        return output

    def json(self):
        f = StringIO.StringIO()
        json_data = []

        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
            json_data.append(OrderedDict(zip(self._headers, self._prepare(org))))

        json.dump(json_data, f)
        output = f.getvalue()
        f.close()
        p.toolkit.response.headers['Content-type'] = 'application/json'
        return output

    def xml(self):
        f = StringIO.StringIO()

        fields = list(self._headers)
        fields.pop(1)

        xml = ['<?xml version="1.0" encoding="UTF-8" ?>']
        _observations = '   <{}>{}</{}>'
        xml.append('<iati-publishers-list>')

        _org_data = PublishersListDownload._get_publisher_data()
        for org in _org_data:
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
        f = StringIO.StringIO()
        wb = Workbook(encoding='utf-8')
        sheet1 = wb.add_sheet('IATI Publishers List')
        _org_data = PublishersListDownload._get_publisher_data()

        # Write Headers
        for _index, _field in enumerate(self._headers):
            sheet1.write(0, _index, _field)

        # Write Rows and Values
        for _row, org in enumerate(_org_data, 1):
            _dt = self._prepare(org)
            # Write Items
            for _col, _item in enumerate(_dt):
                sheet1.write(_row, _col, _item)

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

