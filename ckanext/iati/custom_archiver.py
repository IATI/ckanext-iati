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

from pylons import config


from ckan import model
import ckan.plugins.toolkit as toolkit
from ckanext.iati.helpers import extras_to_dict, extras_to_list
from ckanext.iati.lists import IATI_STANDARD_VERSIONS
from ckanext.archiver import tasks

log = logging.getLogger('iati_archiver')
# Max content-length of archived files, larger files will be ignored
MAX_CONTENT_LENGTH = 50000000
URL_TIMEOUT = 120
DATA_FORMATS = ['xml', 'iati-xml', 'application/xml', 'text/xml', 'text/html', 'application/octet-stream']




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
    }

    results = []

    if not context['site_url']:
        raise Exception('You have to set the "ckan.site_url" property in the '
                        'config file')
        return False
    if not context['user']:
        raise Exception('You have to set the "iati.admin_user.name" property '
                        'in the config file')
        return False
    if not context['apikey']:
        raise Exception('You have to set the "iati.admin_user.api_key" '
                        'property in the config file')
        return False


    # if we are updating a publisher
    publisher_update = False


    if package_id:
        package_ids = [package_id]
    elif publisher_id:
        try:
            print 'checking publisher: '+ publisher_id
            org = toolkit.get_action('organization_show')(context,
                                                          {'id': publisher_id,
                                                           'include_datasets': True})
        except toolkit.ObjectNotFound:
            res = {}
            log.error('Could not find Publisher: {0}'.format(publisher_id))
            res['publisher_id'] = pub_id
            res['issue_type'] = "unknown publisher"
            res['issue_message'] = 'Could not find Publisher: {0}'.format(publisher_id)
            results.append(res)
            return results

        package_ids = [p['name'] for p in org['packages']]
        publisher_update = True
    else:
        try:
            package_ids = toolkit.get_action('package_list')(context, {})
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
    log.info('Number of datasets to archive: {0}'.format(len(package_ids)))


    updated = 0
    consecutive_errors = 0


    for package_id in package_ids:
        result = {}
        updated_package = False
        try:
            updated_package, issue_type, issue_message = archive_package(package_id, context, consecutive_errors)
            print "========= checking package ========" +package_id
            result['publisher_id'] = pub_id
            result['package_id'] = package_id
            result['issue_type'] = issue_type
            result['issue_message'] = issue_message

            results.append(result)

        except Exception, e:
            consecutive_errors += 1
            log.error('Error downloading resource for dataset {0}: '
                      '{1}'.format(package_id, str(e)))
            log.error(text_traceback())
            result['publisher_id'] = pub_id
            result['package_id'] = package_id
            result['issue_message'] = 'Error downloading resource for dataset {0}: {1}'.format(package_id, str(e))
            result['issue_type'] = 'Download Error'


            if consecutive_errors > 15:
                log.error('Too many errors...')
                result['publisher_id'] = pub_id
                result['package_id'] = package_id
                result['issue_message'] = 'Too many errors'
                result['issue_type'] = 'Too many errors'
                if publisher_update:
                    log.error ('Aborting... The publisher can not be reached.')
                    result['publisher_id'] = pub_id
                    result['package_id'] = package_id
                    result['issue_message'] = 'The publisher can not be reached.'
                    result['issue_type'] = 'publisher unreachable'
                    return result
                else:
                    continue
            else:
                consecutive_errors = 0
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
        except tasks.LinkCheckerError, e:
            if 'URL unobtainable: HTTP' in str(e):
                #TODO: What does this do?
                message = str(e)[:str(e).find(' on')]
            else:
                message = str(e)
            return save_package_issue(context, package, extras_dict,
                                      'url-error', message)
        except tasks.DownloadError, e:
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
        except etree.XMLSyntaxError, e:
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
                                               'count(//iati-activity)'))


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
            except ValueError, e:
                log.error('Wrong date format for data_updated for dataset {0}:'
                          ' {1}'.format(package['name'], str(e)))


        # Check dates
        if last_updated_date:
            fmt = '%Y-%m-%d %H:%M:%S'
            new_extras['data_updated'] = last_updated_date.strftime(fmt)
        else:
            new_extras['data_updated'] = None


        for key, value in new_extras.iteritems():
            if (value and (not key in extras_dict or
                           unicode(value) != unicode(extras_dict[key]))):
                update = True
                old_value = (unicode(extras_dict[key]) if
                             key in extras_dict else '""')
                log.info('Updated extra {0} for dataset {1}: {2} -> '
                         '{3}'.format(key, package['name'], old_value, value))
                extras_dict[unicode(key)] = unicode(value)


        # At this point, any previous issues should be resolved,
        # delete the issue extras to mark them as resolved
        if 'issue_type' in extras_dict:
            update = True
            for key in ['issue_type', 'issue_message', 'issue_date']:
                if key in extras_dict:
                    extras_dict[key] = None


        if update:
            package['extras'] = extras_to_list(extras_dict)
            return update_package(context, package), None, None


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
        extras_dict[u'issue_type'] = unicode(issue_type)
        extras_dict[u'issue_message'] = unicode(issue_message)
        extras_dict[u'issue_date'] = (unicode(
                                      datetime.datetime.now().isoformat()))
        data_dict['extras'] = extras_to_list(extras_dict)


        log.error('Issue found for dataset {0}: {1} - '
                  '{2}'.format(data_dict['name'], issue_type, issue_message))


        return update_package(context, data_dict), issue_type, issue_message




def update_package(context, data_dict, message=None):
    context['id'] = data_dict['id']
    message = (message or 'Daily archiver: update dataset '
               '{0}'.format(data_dict['name']))
    context['message'] = message


    for extra in data_dict['extras']:
        data_dict[extra['key']] = extra['value']


    data_dict['extras'] = []


    updated_package = toolkit.get_action('package_update')(context, data_dict)
    log.debug('Package {0} updated with new extras'.format(data_dict['name']))


    return updated_package


def _save_resource(resource, response, max_file_size, chunk_size=1024*16):
    """
    Write the response content to disk.
    Returns a tuple:
        (file length: int, content hash: string, saved file path: string)
    """
    resource_hash = hashlib.sha1()
    length = 0

    fd, tmp_resource_file_path = tempfile.mkstemp()

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

    content_hash = unicode(resource_hash.hexdigest())
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


    user_agent_string = config.get('ckanext.archiver.user_agent_string', None)


    def _download_resource(resource_url, timeout):
        request_headers = {}
        log.info('User agent: {0}'.format(user_agent_string))
        if user_agent_string is not None:
            request_headers['User-Agent'] = user_agent_string
        # Part of 403 url error - if user agent is missing or
        # some sites do not accept IATI (CKAN) as user agent.
        # hence setting default user agent to Mozilla/5.0.
        try:
            res = requests.get(resource['url'], timeout=url_timeout,
                               headers=request_headers, verify=False)
        except Exception, e:
            request_headers['User-Agent'] = 'Mozilla/5.0'
            res = requests.get(resource['url'], timeout=url_timeout,
                               headers=request_headers, verify=False)
        return res


    try:
        headers = json.loads(tasks.link_checker(link_context, link_data))
    except tasks.LinkHeadMethodNotSupported, e:
        res = _download_resource(resource_url=resource['url'],
                                 timeout=url_timeout)
        headers = res.headers
    except tasks.LinkCheckerError, e:
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
        if resource_changed:
            tasks._update_resource(context, resource, log)
        # record fact that resource is too large to archive
        raise tasks.DownloadError("Content-length {0} exceeds maximum allowed"
                                  "value {1}".format(cl, max_content_length))


    # check that resource is a data file
    if not (resource_format in data_formats or ct.lower().strip('"') in data_formats):
        if resource_changed:
            tasks._update_resource(context, resource, log)
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
    #length = res.headers.get('Content-Length', 0)


    # check if resource size changed
    if unicode(length) != resource.get('size'):
        resource_changed = True
        resource['size'] = unicode(length)


    # check that resource did not exceed maximum size when being saved
    # (content-length header could have been invalid/corrupted, or not accurate
    # if resource was streamed)
    #
    # TODO: remove partially archived file in this case
    if length >= max_content_length:
        if resource_changed:
            tasks._update_resource(context, resource, log)
        # record fact that resource is too large to archive
        raise tasks.DownloadError("Content-length after streaming reached "
                                  "maximum allowed value of "
                                  "{0}".format(max_content_length))


    # update the resource metadata in CKAN if the resource has changed
    # IATI: remove generated time tags before calculating the hash
    with open(saved_file, 'r') as f:
        content = f.read()
    content = re.sub(r'generated-datetime="[^"]+"', '', content)


    resource_hash = hashlib.sha1()
    resource_hash.update(content)
    resource_hash = unicode(resource_hash.hexdigest())


    if resource.get('hash') != resource_hash:
        resource['hash'] = resource_hash


    return {'length': length,
            'hash': resource_hash,
            'headers': headers,
            'saved_file': saved_file}
