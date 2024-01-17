import sys
import os
import datetime
from dateutil.parser import parse as date_parser
import hashlib
import socket
import re
from lxml import etree
import requests
import json
import cgitb
import warnings
import logging
import tempfile
from ckan.plugins.toolkit import config, _
from ckan import model
import ckan.plugins.toolkit as toolkit
import ckan.logic as logic
from ckanext.iati.helpers import extras_to_dict, extras_to_list
from ckanext.iati.lists import IATI_STANDARD_VERSIONS
from ckanext.archiver import tasks
from ckanext.iati.logic import validators as iati_validators
from ckanext.iati.linkchecker_patch import link_checker as checker
from ckan.lib.navl.dictization_functions import Invalid

# Disable warning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


tasks.link_checker = checker

log = logging.getLogger(__name__)
# Max content-length of archived files, larger files will be ignored
MAX_CONTENT_LENGTH = int(config.get('ckanext-archiver.max_content_length',
                                    60000000))
URL_TIMEOUT = 100
DATA_FORMATS = ['xml', 'iati-xml', 'application/xml', 'text/xml', 'text/html', 'application/octet-stream']


def parse_error_message(e):
    """
    This is used to parse the error message
    :param e:
    :return:
    """
    message_list = []
    _attributes = ('error_summary', 'message')
    for attr in _attributes:
        if hasattr(e, attr) and getattr(e, attr):
            error_value = getattr(e, attr)
            if isinstance(error_value, dict):
                for k in error_value:
                    message_list.append(error_value[k])
            elif error_value:
                message_list.append(error_value)
    return ' '.join(message_list)


def text_traceback():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = 'the original traceback:'.join(
            cgitb.text(sys.exc_info()).split('the original traceback:')[1:]
        ).strip()
    return res


def run(package_id=None, publisher_id=None, pub_id=None):
    # TODO: use this when it gets to default ckan
    # username = toolkit.get_action('get_site_user')({'model': model,
    #                                                 'ignore_auth': True}, {})
    context = {
        'model': model,
        'session': model.Session,
        'site_url': config.get('ckan.site_url'),
        'user': config.get('iati.admin_user.name'),
        'apikey': config.get('iati.admin_user.api_key'),
        'api_version': 3,
        'disable_archiver': True
    }

    results = []

    if not context['site_url']:
        raise Exception('You have to set the "ckan.site_url" property in the '
                        'config file')
    if not context['user']:
        raise Exception('You have to set the "iati.admin_user.name" property '
                        'in the config file')
    if not context['apikey']:
        raise Exception('You have to set the "iati.admin_user.api_key" '
                        'property in the config file')

    # if we are updating a publisher
    publisher_update = False

    if package_id:
        package_ids = [package_id]
    elif publisher_id:
        try:
            toolkit.get_action('organization_show')(context, {'id': publisher_id, 'include_datasets': False})
        except toolkit.ObjectNotFound:
            res = {}
            log.error('Could not find Publisher: {0}'.format(publisher_id))
            res['publisher_id'] = pub_id
            res['issue_type'] = "unknown publisher"
            res['issue_message'] = 'Could not find Publisher: {0}'.format(publisher_id)
            results.append(res)
            return results

        package_search = toolkit.get('package_search')(
            context, {
                "fq": 'owner_org:{}'.format(organization['id']),
                "rows": 1000  # unlikely 1 single organization crossing 1000 dataset
            })
        package_ids = [p['id'] for p in package_search]
        publisher_update = True
    else:
        try:
            #TODO: we need to write an iterator with limit and offset to get package by package
            # as no of packages grow
            package_ids = toolkit.get_action('package_list')(context, {"limit": 1000000})
        except toolkit.ObjectNotFound:
            res = {}
            log.error('Could not find package: {0}'.format(package_id))
            res['publisher_id'] = pub_id
            res['issue_type'] = "unknown package"
            res['issue_message'] = 'Could not find package: {0}'.format(package_id)
            results.append(res)
            return results

    t1 = datetime.datetime.now()
    log.info('IATI Archiver: starting {0}'.format(str(t1)))
    log.info('Number of datasets to archive: {0}'.format(str(len(package_ids))))
    consecutive_errors = 0
    updated = 0
    total_packages_cnt = len(package_ids)
    for cnt, package_id in enumerate(package_ids, 1):
        result = {}
        updated_package = False
        log.info("Processing package: {} : Count {}/{}".format(package_id, str(cnt), str(total_packages_cnt)))
        try:
            updated_package, issue_type, issue_message = archive_package(package_id, context, consecutive_errors)
            result['publisher_id'] = pub_id
            result['package_id'] = package_id
            result['issue_type'] = issue_type
            result['issue_message'] = issue_message
            results.append(result)
        except logic.ValidationError as e:
            msg = parse_error_message(e)
            log.error(msg)
            result['publisher_id'] = pub_id
            result['package_id'] = package_id
            result['issue_message'] = msg
            result['issue_type'] = 'Validation Error'
            save_package_core_validation_issue(package_id, msg)
        except Exception as e:
            log.error('Error downloading resource for dataset {0}: '
                      '{1}'.format(package_id, str(e)))
            log.error(text_traceback())
            result['publisher_id'] = pub_id
            result['package_id'] = package_id
            result['issue_message'] = 'Error downloading resource for dataset {0}: {1}'.format(package_id, str(e))
            result['issue_type'] = 'Download Error'

        if updated_package:
            updated += 1
        results.append(result)

    return results


def archive_package(package_id, context, consecutive_errors=0):

    from ckanext.archiver import tasks
    package = toolkit.get_action('package_show')(context, {'id': package_id})
    extras_dict = extras_to_dict(package)
    is_activity_package = (True if 'activity' == extras_dict.get('filetype')
                           else False)
    log.info('Archiving dataset: {0} ({1} resources)'.format(
              package.get('name'), len(package.get('resources', []))))
    for resource in package.get('resources', []):
        if not resource.get('url', ''):
            return save_package_issue(context, package, extras_dict, 'no-url',
                                      'URL missing')
        old_hash = resource.get('hash')
        try:
            result = download(context, resource, data_formats=DATA_FORMATS)
        except tasks.LinkCheckerError as e:
            if 'URL unobtainable: HTTP' in str(e):
                #TODO: What does this do?
                message = str(e)[:str(e).find(' on')]
            else:
                message = str(e)
            return save_package_issue(context, package, extras_dict,
                                      'url-error', message)
        except tasks.DownloadError as e:
            if 'exceeds maximum allowed value' in str(e):
                message = 'File too big, not downloading'
            else:
                message = str(e)
            return save_package_issue(context, package, extras_dict,
                                      'download-error', message)
        except socket.timeout:
            return save_package_issue(context, package, extras_dict,
                                      'download-error', 'URL timeout')
        file_path = result['saved_file']
        if 'zip' in result['headers'].get('content-type', ''):
            # Skip zipped files for now
            log.info('Skipping zipped file for dataset '
                     '{0}'.format(package.get('name')))
            os.remove(file_path)
            continue

        update = False
        if old_hash != result.get('hash'):
            update = True

        with open(file_path, 'r') as f:
            xml = f.read()
        os.remove(file_path)

        if (re.sub('<!doctype(.*)>', '',
                   xml.lower()[:100]).strip().startswith('<html')):
            return save_package_issue(context, package, extras_dict,
                                      'xml-error', 'File is an HTML document')

        try:
            tree = etree.fromstring(xml, parser=etree.XMLParser(huge_tree=True))
        except etree.XMLSyntaxError as e:
            return save_package_issue(context, package, extras_dict,
                                      'xml-error', 'Could not parse XML file:'
                                      ' {0}'.format(str(e)[:200]))

        filetype = 'unchecked'
        if tree.tag == 'iati-activities':
            filetype = 'activity'

        if tree.tag == 'iati-organisations':
            filetype = 'organisation'

        if is_activity_package and filetype != 'activity':
            return save_package_issue(context, package, extras_dict,
                                      'metadata error', 'Check the filetype metadata field')

        if not is_activity_package and filetype != 'organisation':
            return save_package_issue(context, package, extras_dict,
                                      'metadata error', 'Check the filetype metadata field')
  
        new_extras = {}
        # IATI standard version (iati_version extra)
        xpath = '/iati-activities/@version | /iati-organisations/@version'
        version = tree.xpath(xpath)
        log.info(version)
        log.info(version[0])
        allowed_versions = IATI_STANDARD_VERSIONS
        if len(version) and version[0] in allowed_versions:
            version = version[0]
        else:
            version = 'n/a'
        new_extras['iati_version'] = version

        if is_activity_package:
            # Number of activities (activity_count extra)
            new_extras['activity_count'] = int(tree.xpath(
                                               'count(/iati-activities/iati-activity)'))

        # Last updated date (data_updated extra)
        if is_activity_package:
            xpath = 'iati-activity/@last-updated-datetime'
        else:
            xpath = 'iati-organisation/@last-updated-datetime'

        dates = tree.xpath(xpath) or []
        dates = sorted(dates, reverse=True)
        last_updated_date = None
        for date in dates:
            try:
                check_date = date_parser(date).replace(tzinfo=None)
                if check_date < datetime.datetime.now():
                    last_updated_date = check_date
                    break
            except ValueError as e:
                log.error('Wrong date format for data_updated for dataset {0}:'
                          ' {1}'.format(package['name'], str(e)))

        # Check dates
        if last_updated_date:
            fmt = '%Y-%m-%d %H:%M:%S'
            new_extras['data_updated'] = last_updated_date.strftime(fmt)
        else:
            new_extras['data_updated'] = None

        for key, value in new_extras.items():
            if value and (key not in extras_dict or str(value) != str(extras_dict.get(key, ''))):
                log.info("Identified update")
                update = True
                old_value = (str(extras_dict[key]) if key in extras_dict else '')
                log.info('Updated extra {0} for dataset {1}: {2} -> '
                         '{3}'.format(key, package['name'], old_value, value))
                extras_dict[str(key)] = str(value)

        # At this point, any previous issues should be resolved,
        # delete the issue extras to mark them as resolved
        if 'issue_type' in extras_dict:
            update = True
            for key in ['issue_type', 'issue_message', 'issue_date']:
                if key in extras_dict:
                    extras_dict[key] = None

        log.info("Is package: {} is update? - {}".format(package.get('name', ''), str(update)))
        if update:
            package['extras'] = extras_to_list(extras_dict)
            return update_package(context, package), None, None
    log.info("************** Done **********")
    return None, None, None


def save_package_issue(context, data_dict, extras_dict, issue_type,
                       issue_message):
    if 'issue_type' in extras_dict and 'issue_message' in extras_dict \
            and extras_dict['issue_type'] == issue_type \
            and extras_dict['issue_message'] == issue_message:
        log.info('Dataset {0} still has the same issue ({1} - {2}), '
                 'skipping...'.format(data_dict['name'], issue_type,
                                      issue_message))
        return None, issue_type, issue_message
    else:
        extras_dict['issue_type'] = str(issue_type)
        extras_dict['issue_message'] = str(issue_message)
        extras_dict['issue_date'] = (str(
                                      datetime.datetime.now().isoformat()))
        data_dict['extras'] = extras_to_list(extras_dict)
        log.error('Issue found for dataset {0}: {1} - '
                  '{2}'.format(data_dict['name'], issue_type, issue_message))

        return update_package(context, data_dict), issue_type, issue_message


def save_package_core_validation_issue(pkg_id, issue_message):
    """
    Archiver fails to update the package if the package already have some validation error
    :param pkg_id: str
    :param issue_message: str
    :return: None
    """
    log.info("Saving core validation issue")
    log.info(issue_message)
    issue_type = 'archiver-failed'
    issue_date = str(datetime.datetime.utcnow())
    issue_message = "Archiver failed to update package due to existing validation error. " + issue_message
    try:
        package = model.Package.get(pkg_id)
        package.extras['issue_type'] = issue_type
        package.extras['issue_date'] = issue_date
        package.extras['issue_message'] = issue_message
        model.Session.commit()
    except Exception as e:
        log.error("Error while saving the core issue in save_package_core_validation_issue")
        log.error(e)
    return None


def update_package(context, data_dict, message=None):
    log.info("Updating package: {}".format(data_dict.get('name', '')))
    context['id'] = data_dict['id']
    message = (message or 'Daily archiver: update dataset '
               '{0}'.format(data_dict['name']))
    context['message'] = message
    context['disable_archiver'] = True
    for extra in data_dict['extras']:
        data_dict[extra['key']] = extra['value']
    data_dict['extras'] = []
    data_dict = patch_invalid_country_code(context, data_dict)
    updated_package = toolkit.get_action('package_update')(context, data_dict)
    log.info('Package {0} updated with new extras'.format(data_dict['name']))
    return updated_package


def patch_invalid_country_code(context, data_dict):
    """
    This to patch the invalid country codes to ''
    :param context: dict
    :param data_dict: dict
    :return: dict
    """
    country = data_dict.get('country', '')
    if country:
        try:
            iati_validators.country_code(country, context)
        except Invalid as e:
            data_dict['country'] = ''
    return data_dict


def _save_resource(resource, response, max_file_size, chunk_size=1024*16):
    """
    Write the response content to disk.
    Returns a tuple:
        (file length: int, content hash: string, saved file path: string)
    """
    resource_hash = hashlib.sha1()
    length = 0

    fd, tmp_resource_file_path = tempfile.mkstemp()
    log.info("Max file size given")
    log.info(max_file_size)

    with open(tmp_resource_file_path, 'wb') as fp:
        for chunk in response.iter_content(chunk_size=chunk_size,
                                           decode_unicode=False):
            fp.write(chunk)
            length += len(chunk)
            resource_hash.update(chunk)

            if length >= max_file_size:
                fp.close()
                os.remove(tmp_resource_file_path)
                raise tasks.ChooseNotToDownload(
                    _("Content-length %s exceeds maximum allowed value %s") %
                    (length, max_file_size))

    os.close(fd)

    content_hash = str(resource_hash.hexdigest())
    return length, content_hash, tmp_resource_file_path


def download(context, resource, url_timeout=URL_TIMEOUT,
             max_content_length=MAX_CONTENT_LENGTH,
             data_formats=DATA_FORMATS):
    res = None
    resource_changed = False

    link_context = "{}"
    link_data = json.dumps({
        'url': resource['url'],
        'url_timeout': url_timeout
    })
    user_agent_string = config.get('ckanext.archiver.user_agent_string',
                                   'curl/7.35.0')

    def _download_resource(resource_url, timeout):
        _request_headers = {'User-Agent': user_agent_string}
        # Part of 403 url error - if user agent is missing or
        # some sites do not accept IATI (CKAN) as user agent.
        # hence setting default user agent to Mozilla/5.0.
        try:
            response = requests.get(resource['url'], timeout=url_timeout,
                                    headers=_request_headers, verify=True)
        except Exception as e:
            request_headers['User-Agent'] = 'curl/7.35.0'
            response = requests.get(resource['url'], timeout=url_timeout,
                                    headers=_request_headers, verify=False)
        return response

    try:
        headers = json.loads(tasks.link_checker(link_context, link_data))
    except tasks.LinkHeadMethodNotSupported as e:
        res = _download_resource(resource_url=resource['url'],
                                 timeout=url_timeout)
        headers = res.headers
    except tasks.LinkCheckerError as e:
        if any(x in str(e).lower() for x in ('internal server error', '403',
                                             )):
            # If the HEAD method is not supported or if a 500
            # error is returned we'll handle the download manually
            res = _download_resource(resource_url=resource['url'],
                                     timeout=url_timeout)
            headers = res.headers
        else:
            raise

    resource_format = resource.get('format', '').lower()
    ct = tasks._clean_content_type(headers.get('content-type', '').lower())
    cl = headers.get('content-length')
    if resource.get('mimetype') != ct:
        resource_changed = True
        resource['mimetype'] = ct

    # this is to store the size in case there is an error, but the real size
    # check is done after dowloading the data file, with its real length
    if cl is not None and (resource.get('size') != cl):
        resource_changed = True
        resource['size'] = cl

    # make sure resource content-length does not exceed our maximum
    if cl and int(cl) >= max_content_length:
        # CKAN 2.9 doesnt support pylons config. Hence removing _update_resource
        raise tasks.DownloadError("Content-length {0} exceeds maximum allowed"
                                  "value {1}".format(cl, max_content_length))

    # check that resource is a data file
    if not (resource_format in data_formats or ct.lower().strip('"') in data_formats):
        # CKAN 2.9 doesnt support pylons config. Hence removing _update_resource
        raise tasks.DownloadError("Of content type {0}, not "
                                  "downloading".format(ct))

    # get the resource and archive it
    # TODO: remove the Accept-Encoding limitation after upgrading
    # archiver and requests
    if not res:
        request_headers = {
            'Accept-Encoding': ''
        }
        if user_agent_string is not None:
            request_headers['User-Agent'] = user_agent_string
        res = requests.get(resource['url'], timeout=url_timeout,
                           headers=request_headers, verify=False)
    length, hash, saved_file = _save_resource(resource, res, max_content_length)

    # check if resource size changed
    if str(length) != resource.get('size'):
        resource_changed = True
        resource['size'] = str(length)

    # check that resource did not exceed maximum size when being saved
    # (content-length header could have been invalid/corrupted, or not accurate
    # if resource was streamed)
    #
    # TODO: remove partially archived file in this case
    if length >= max_content_length:
        # CKAN 2.9 doesnt support pylons config. Hence removing _update_resource
        # record fact that resource is too large to archive
        raise tasks.DownloadError("Content-length after streaming reached "
                                  "maximum allowed value of "
                                  "{0}".format(max_content_length))

    # update the resource metadata in CKAN if the resource has changed
    # IATI: remove generated time tags before calculating the hash
    with open(saved_file, 'rb') as f:
        content_bytes = f.read()
        content_str = content_bytes.decode('utf-8')
        content_str = re.sub(r'generated-datetime="[^"]+"', '', content_str)

    resource_hash = hashlib.sha1()
    resource_hash.update(content_str.encode('utf-8'))
    resource_hash = str(resource_hash.hexdigest())

    if resource.get('hash') != resource_hash:
        resource['hash'] = resource_hash

    return {'length': length,
            'hash': resource_hash,
            'headers': headers,
            'saved_file': saved_file}
