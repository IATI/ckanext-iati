import os
from lxml import etree
import requests
import json
from pylons import config
from ckan.lib.cli import CkanCommand
from ckan.logic import get_action
from ckan import model

from ckan.lib.helpers import date_str_to_datetime
from ckanext.archiver import tasks
import logging

log = logging.getLogger(__name__)

class Archiver(CkanCommand):
    '''
    Download and save copies of all IATI activity files, extract some metrics
    from them and store them as extras.

    Usage:

        paster iati-archiver update [{package-id}]
           - Archive all activity files or just those belonging to a specific package
             if a package id is provided

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    min_args = 0
    max_args = 2
    pkg_names = []

    def command(self):
        '''
        Parse command line arguments and call appropriate method.
        '''
        if not self.args or self.args[0] in ['--help', '-h', 'help']:
            print Archiver.__doc__
            return

        cmd = self.args[0]
        self._load_config()
        # TODO: use this when it gets to default ckan
        # username = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        context = {
            'model': model,
            'session':model.Session,
            'site_url':config.get('ckan.site_url'),
            'user': config.get('iati.admin_user.name'),
            'apikey': config.get('iati.admin_user.api_key')
        }

        if cmd == 'update':
            if len(self.args) > 1:
                packages = [unicode(self.args[1])]

            else:
                packages = get_action('package_list')(context, {})

            data_formats = tasks.DATA_FORMATS
            data_formats.append('iati-xml')

            log.info('Number of datasets to archive: %d' % len(packages))
            updated = 0
            for package_id in packages:
                package = get_action('package_show_rest')(context,{'id': package_id})


                is_activity_package = (package['extras']['filetype'] == 'activity') if 'filetype' in package['extras'] else 'activity'

                log.info('Archiving dataset: %s (%d resources)' % (package.get('name'), len(package.get('resources', []))))
                for resource in package.get('resources', []):

                    if not resource.get('url',''):
                        log.error('Resource for dataset %s does not have URL' % package['name'])
                        continue

                    try:
                        result = tasks.download(context,resource,data_formats=data_formats)
                    except tasks.LinkCheckerError,e:
                        if 'method not allowed' in str(e).lower():
                            # The DFID server does not support HEAD requests*,
                            # so we need to handle the download manually
                            # * But only the first time a file is downloaded!?
                            result = _download_resource(context,resource,data_formats=data_formats)
                        else:
                            log.error('Invalid resource URL: %s' % str(e))
                            continue
                    except tasks.DownloadError:
                        log.error('Error downloading resource: %s' % str(e))
                        continue

                    if 'zip' in result['headers']['content-type']:
                        # Skip zipped files for now
                        log.info('Skipping zipped file for dataset %s ' % package.get('name'))
                        continue

                    file_path = result['saved_file']
                    f = open(file_path,'r')
                    xml = f.read()
                    f.close()
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
                            log.error('Wrong date format for data_updated: %s' % str(e))


                    update = False
                    for key,value in new_extras.iteritems():
                        if value and (not key in package['extras'] or value != package['extras'][key]):
                            update = True
                            old_value = package['extras'][key] if key in package['extras'] else '""'
                            log.info('Updated extra %s for dataset %s: %s -> %s' % (key,package['name'],old_value,value))
                            package['extras'][key] = value

                    if update:
                        context['id'] = package['id']
                        updated_package = get_action('package_update_rest')(context,package)
                        log.info('Package %s updated with new extras' % package['name'])
                        updated = updated + 1
            log.info('Done. Updated %i packages' % updated)
        else:
            log.error('Command %s not recognized' % (cmd,))

def _download_resource(context,resource, max_content_length=50000000, url_timeout=30,data_formats=['xml','iati-xml']):

    # get the resource and archive it
    #logger.info("Resource identified as data file, attempting to archive")
    res = requests.get(resource['url'], timeout = url_timeout)

    headers = res.headers
    resource_format = resource['format'].lower()
    ct = headers.get('content-type', '').lower()
    cl = headers.get('content-length')

    resource_changed = (resource.get('mimetype') != ct) or (resource.get('size') != cl)
    if resource_changed:
        resource['mimetype'] = ct
        resource['size'] = cl

    length, hash, saved_file = tasks._save_resource(resource, res, max_content_length)

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

    # update the resource metadata in CKAN
    resource['hash'] = hash
    tasks._update_resource(context, resource)

    return {'length': length,
            'hash' :hash,
            'headers': headers,
            'saved_file': saved_file}

