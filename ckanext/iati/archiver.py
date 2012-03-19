import sys
import os
import datetime
import hashlib
import re
from lxml import etree
import requests
import json
from pylons import config
from ckan.logic import get_action
from ckan import model

from ckan.lib.helpers import date_str_to_datetime
import logging

log = logging.getLogger('iati_archiver')

import cgitb
import warnings
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
DATA_FORMATS = ['xml','iati-xml','application/xml']

def run(package_id=None):

    # TODO: use this when it gets to default ckan
    # username = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
    context = {
        'model': model,
        'session':model.Session,
        'site_url':config.get('ckan.site_url'),
        'user': config.get('iati.admin_user.name'),
        'apikey': config.get('iati.admin_user.api_key')
    }

    if package_id:
        package_ids = [package_id]
    else:
        package_ids = get_action('package_list')(context, {})

    t1 = datetime.datetime.now()

    from ckanext.archiver import tasks

    log.info('IATI Archiver: starting  %s' % str(t1))
    log.info('Number of datasets to archive: %d' % len(package_ids))
    updated = 0
    consecutive_errors = 0
    for package_id in package_ids:
        package = get_action('package_show_rest')(context,{'id': package_id})

        is_activity_package = (package['extras']['filetype'] == 'activity') if 'filetype' in package['extras'] else 'activity'

        log.debug('Archiving dataset: %s (%d resources)' % (package.get('name'), len(package.get('resources', []))))
        for resource in package.get('resources', []):

            if not resource.get('url',''):
                log.error('Resource for dataset %s does not have URL' % package['name'])
                continue

            old_hash = resource.get('hash')
            try:
                result = download(context,resource,data_formats=DATA_FORMATS)
            except tasks.LinkCheckerError,e:
                log.error('Invalid resource URL for dataset %s: %s' % (package['name'],str(e)))
                continue
            except tasks.DownloadError,e:
                log.error('Error downloading resource for dataset %s: %s' % (package['name'],str(e)))
                continue
            except Exception,e:
                consecutive_errors = consecutive_errors + 1
                log.error('Error downloading resource for dataset %s: %s' % (package['name'],str(e)))
                log.error(text_traceback())
                if consecutive_errors > 5:
                    log.error('Too many errors, aborting...')
                    return False
                else:
                    continue
            else:
                consecutive_errors = 0

            if 'zip' in result['headers']['content-type']:
                # Skip zipped files for now
                log.info('Skipping zipped file for dataset %s ' % package.get('name'))
                continue

            update = False

            if old_hash != resource.get('hash'):
                update = True

            file_path = result['saved_file']

            with open(file_path, 'r') as f:
                xml = f.read()
            os.remove(file_path)

            try:
                tree = etree.fromstring(xml)
            except etree.XMLSyntaxError,e:
                log.error('Could not parse XML file for dataset %s: %s' % (package['name'],str(e)))
                continue

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

            sorted(dates,reverse=True)
            last_updated_date = dates[0] if len(dates) else None

            # Check dates
            if last_updated_date:
                # Get rid of the microseconds
                if '.' in last_updated_date:
                    last_updated_date = last_updated_date[:last_updated_date.find('.')]
                try:
                    date = date_str_to_datetime(last_updated_date)
                    format = '%Y-%m-%d %H:%M' if (date.hour and date.minute) else '%Y-%m-%d'
                    new_extras['data_updated'] = date.strftime(format)
                except (ValueError,TypeError),e:
                    log.error('Wrong date format for data_updated for dataset %s: %s' % (package['name'],str(e)))


            for key,value in new_extras.iteritems():
                if value and (not key in package['extras'] or unicode(value) != unicode(package['extras'][key])):
                    update = True
                    old_value = unicode(package['extras'][key]) if key in package['extras'] else '""'
                    log.info('Updated extra %s for dataset %s: %s -> %s' % (key,package['name'],old_value,value))
                    package['extras'][unicode(key)] = unicode(value)

            if update:
                context['id'] = package['id']
                updated_package = get_action('package_update_rest')(context,package)
                log.debug('Package %s updated with new extras' % package['name'])
                updated = updated + 1

    t2 = datetime.datetime.now()

    log.info('IATI Archiver: Done. Updated %i packages. Total time: %s' % (updated,str(t2 - t1)))

    return True

def download(context, resource, url_timeout=URL_TIMEOUT,
             max_content_length=MAX_CONTENT_LENGTH,
             data_formats=DATA_FORMATS):

    from ckanext.archiver import tasks

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
    if not (resource_format in data_formats or ct.lower() in data_formats):
        if resource_changed:
            tasks._update_resource(context, resource)
        raise tasks.DownloadError("Of content type %s, not downloading" % ct)

    # get the resource and archive it
    res = requests.get(resource['url'], timeout = url_timeout)
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

