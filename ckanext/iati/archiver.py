import sys
import os
import datetime
import hashlib
import socket
import re
from lxml import etree
import requests
import json
import cgitb
import warnings
import logging

from pylons import config

from ckan import model
import ckan.plugins.toolkit as toolkit
import ckan.iati.helpers.extras_to_dict as extras_to_dict

log = logging.getLogger('iati_archiver')


def text_traceback():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = 'the original traceback:'.join(
            cgitb.text(sys.exc_info()).split('the original traceback:')[1:]
        ).strip()
    return res

# Max content-length of archived files, larger files will be ignored
MAX_CONTENT_LENGTH = 50000000
URL_TIMEOUT=30
DATA_FORMATS = ['xml','iati-xml','application/xml', 'text/xml', 'text/html']

def run(package_id=None, publisher_id=None):

    # TODO: use this when it gets to default ckan
    # username = toolkit.get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
    context = {
        'model': model,
        'session':model.Session,
        'site_url':config.get('ckan.site_url'),
        'user': config.get('iati.admin_user.name'),
        'apikey': config.get('iati.admin_user.api_key'),
        'api_version': 3,
    }
    if not context['site_url']:
        raise Exception('You have to set the "ckan.site_url" property in the config file')
        return False
    if not context['user']:
        raise Exception('You have to set the "iati.admin_user.name" property in the config file')
        return False
    if not context['apikey']:
        raise Exception('You have to set the "iati.admin_user.api_key" property in the config file')
        return False

    if package_id:
        package_ids = [package_id]
    elif publisher_id:
        try:
            org = toolkit.get_action('organization_show')(context, {'id': publisher_id})
        except toolkit.ObjectNotFound:
            log.error('Could not find Publisher: {0}'.format(publisher_id))
            sys.exit(1)
        package_ids = [p['name'] for p in org['packages']]
    else:
        try:
            package_ids = toolkit.get_action('package_list')(context, {})
        except toolkit.ObjectNotFound:
            log.error('Could not find package: {0}'.format(package_id))
            sys.exit(1)

    t1 = datetime.datetime.now()

    print ('IATI Archiver: starting {0}'.format(str(t1)))
    print ('Number of datasets to archive: {0}'.format(len(package_ids)))

    updated = 0
    consecutive_errors = 0

    for package_id in package_ids:
        try:
            updated_package = archive_package(package_id, context, consecutive_errors)
        except Exception,e:
            consecutive_errors += 1
            print ('Error downloading resource for dataset %s: %s' % (package_id, str(e)))
            print (text_traceback())
            if consecutive_errors > 5:
                print 'Too many errors, aborting...'
                return False
            else:
                continue
        else:
            consecutive_errors = 0

        if updated_package:
            updated += 1

    t2 = datetime.datetime.now()

    log.info('IATI Archiver: Done. Updated %i packages. Total time: %s' % (updated,str(t2 - t1)))

    return True


def archive_package(package_id, context, consecutive_errors=0):

    from ckanext.archiver import tasks
    package = toolkit.get_action('package_show')(context,{'id': package_id})
    extras_dict = extras_to_dict(package)

    is_activity_package = True if 'activity' == extras_dict.get('filetype') else False

    log.debug('Archiving dataset: {0} ({1} resources)'.format(package.get('name'), len(package.get('resources', []))))
    for resource in package.get('resources', []):

        if not resource.get('url',''):
            return save_package_issue(context, package, 'no-url', 'URL missing')

        old_hash = resource.get('hash')
        try:
            result = download(context,resource,data_formats=DATA_FORMATS)
        except tasks.LinkCheckerError, e:
            if 'URL unobtainable: HTTP' in str(e):
                message = str(e)[:str(e).find(' on')]
            else:
                message = str(e)
            return save_package_issue(context, package, 'url-error', message)
        except tasks.DownloadError, e:
            if 'exceeds maximum allowed value' in str(e):
                message = 'File too big, not downloading'
            else:
                message = str(e)
            return save_package_issue(context, package, 'download-error', message)
        except socket.timeout:
            return save_package_issue(context, package, 'download-error', 'URL timeout')

        file_path = result['saved_file']

        if 'zip' in result['headers'].get('content-type', ''):
            # Skip zipped files for now
            log.info('Skipping zipped file for dataset %s ' % package.get('name'))
            os.remove(file_path)
            continue

        update = False

        if old_hash != resource.get('hash'):
            update = True


        with open(file_path, 'r') as f:
            xml = f.read()
        os.remove(file_path)

        if re.sub('<!doctype(.*)>', '', xml.lower()[:100]).strip().startswith('<html'):
            return save_package_issue(context, package, 'xml-error', 'File is an HTML document')

        try:
            tree = etree.fromstring(xml)
        except etree.XMLSyntaxError, e:
            return save_package_issue(context, package, 'xml-error', 'Could not parse XML file: {0}'.format(str(e)[:200]))

        new_extras = {}
        if is_activity_package:
            # Number of activities (activity_count extra)
            new_extras['activity_count'] = int(tree.xpath('count(//iati-activity)'))

        # Last updated date (data_updated extra)
        if is_activity_package:
            xpath = 'iati-activity/@last-updated-datetime'
        else:
            xpath = 'iati-organisation/@last-updated-datetime'

        dates = tree.xpath(xpath) or []
        dates = sorted(dates,reverse=True)
        last_updated_date = None
        for date in dates:
            try:
                check_date = date_parser(date)
                if check_date < datetime.datetime.now():
                    last_updated_date = check_date
                    break
            except ValueError, e:
                log.error('Wrong date format for data_updated for dataset %s: %s' % (package['name'],str(e)))

        # Check dates
        if last_updated_date:
            format = '%Y-%m-%d %H:%M' if (last_updated_date.hour and last_updated_date.minute) else '%Y-%m-%d'
            new_extras['data_updated'] = last_updated_date.strftime(format)
        else:
            new_extras['data_updated'] = None

        for key,value in new_extras.iteritems():
            if value and (not key in package['extras'] or unicode(value) != unicode(package['extras'][key])):
                update = True
                old_value = unicode(package['extras'][key]) if key in package['extras'] else '""'
                log.info('Updated extra %s for dataset %s: %s -> %s' % (key,package['name'],old_value,value))
                package['extras'][unicode(key)] = unicode(value)


        # At this point, any previous issues should be resolved, delete the issue extras
        # to mark them as resolved
        if 'issue_type' in package['extras']:
            update = True
            for key in ['issue_type', 'issue_message', 'issue_date']:
                if key in package['extras']:
                    package['extras'][key] = None

        if update:
            return update_package(context, package)

    return None

def save_package_issue(context, data_dict, issue_type, issue_message):
    if 'issue_type' in data_dict['extras'] and 'issue_message' in data_dict['extras'] \
        and data_dict['extras']['issue_type'] == issue_type \
        and data_dict['extras']['issue_message'] == issue_message:
        log.info('Dataset {0} still has the same issue ({1} - {2}), skipping...'.format(data_dict['name'], issue_type, issue_message))
        return None
    else:
        data_dict['extras'][u'issue_type'] = unicode(issue_type)
        data_dict['extras'][u'issue_message'] = unicode(issue_message)
        data_dict['extras'][u'issue_date'] = unicode(datetime.datetime.now().isoformat())

        log.error('Issue found for dataset {0}: {1} - {2}'.format(data_dict['name'], issue_type, issue_message))

        return update_package(context, data_dict)

def update_package(context, data_dict, message=None):
    context['id'] = data_dict['id']
    message = message or 'Daily archiver: update dataset %s' % data_dict['name']
    context['message'] = message

    updated_package = toolkit.get_action('package_update_rest')(context, data_dict)
    log.debug('Package %s updated with new extras' % data_dict['name'])

    return updated_package



def download(context, resource, url_timeout=URL_TIMEOUT,
             max_content_length=MAX_CONTENT_LENGTH,
             data_formats=DATA_FORMATS):

    from ckanext.archiver import tasks

    resource_changed = False

    link_context = "{}"
    link_data = json.dumps({
        'url': resource['url'],
        'url_timeout': url_timeout
    })

    try:
        headers = json.loads(tasks.link_checker(link_context, link_data))
    except tasks.LinkCheckerError,e:
        if 'method not allowed' in str(e).lower():
            # The DFID server does not support HEAD requests*,
            # so we need to handle the download manually
            # * But only the first time a file is downloaded!?
            res = requests.get(resource['url'], timeout = url_timeout)
            headers = res.headers
        else:
            raise


    resource_format = resource['format'].lower()
    ct = tasks._clean_content_type( headers.get('content-type', '').lower() )
    cl = headers.get('content-length')

    if resource.get('mimetype') != ct:
        resource_changed = True
        resource['mimetype'] = ct

    # this is to store the size in case there is an error, but the real size check
    # is done after dowloading the data file, with its real length
    if cl is not None and (resource.get('size') != cl):
        resource_changed = True
        resource['size'] = cl

    # make sure resource content-length does not exceed our maximum
    if cl and int(cl) >= max_content_length:
        if resource_changed:
            tasks._update_resource(context, resource)
        # record fact that resource is too large to archive
        raise tasks.DownloadError("Content-length %s exceeds maximum allowed value %s" %
            (cl, max_content_length))

    # check that resource is a data file
    if not ct.lower().strip('"') in data_formats:
        if resource_changed:
            tasks._update_resource(context, resource)
        raise tasks.DownloadError("Of content type %s, not downloading" % ct)

    # get the resource and archive it
    # TODO: remove the Accept-Encoding limitation after upgrading
    # archiver and requests
    res = requests.get(resource['url'], timeout = url_timeout, headers={'Accept-Encoding':''})
    length, hash, saved_file = tasks._save_resource(resource, res, max_content_length)

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
            tasks._update_resource(context, resource)
        # record fact that resource is too large to archive
        raise tasks.DownloadError("Content-length after streaming reached maximum allowed value of %s" %
            max_content_length)

    # update the resource metadata in CKAN if the resource has changed
    # IATI: remove generated time tags before calculating the hash
    content = open(saved_file,'r').read()
    content = re.sub('generated-datetime="(.*)"','',content)

    resource_hash = hashlib.sha1()
    resource_hash.update(content)
    resource_hash = unicode(resource_hash.hexdigest())

    if resource.get('hash') != resource_hash:
        resource['hash'] = resource_hash


    return {'length': length,
            'hash' : resource_hash,
            'headers': headers,
            'saved_file': saved_file}
