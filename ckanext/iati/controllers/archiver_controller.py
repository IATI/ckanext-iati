from ckan.lib.base import render, BaseController
import ckan.lib.jobs as jobs
from .. import custom_archiver as arch
import sys
import json
import ckan.plugins.toolkit as toolkit
from ckan import model
from pylons import config
import logging
from collections import OrderedDict
import ckan.authz as authz
from ckan.lib.base import c
import ckan.logic as logic
import ckan.plugins as p
log = logging.getLogger('iati_archiver')


class ArchiverRunStatus(BaseController):

    def __init__(self):

        self.pkg_stat = None

    def check_status(self, task_id=None):

        result = {}

        if task_id and task_id != 'undefined':

            try:
                job = jobs.job_from_id(id=task_id)
                result.update({'status': job.get_status()})

                if job.result:
                    result['result'] = {}

                    try:

                        result['result'].update(job.result[0])
                        result['result']['task_id'] = task_id

                    except Exception as e:

                        result.update({'status': "failed"})
                        result['result'] = {}
                        result['result']['issue_type'] = "unknown error"
                        result['result']['issue_message'] = "Something went wrong, please try again or contact support."
                        result['result']['task_id'] = task_id

            except Exception as e:
                result.update({'status': "failed"})
                result['result'] = {}
                result['result']['issue_type'] = "unknown error"
                result['result']['issue_message'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""
                result['result']['task_id'] = task_id

        else:
            result.update({'status': 'failed'})
            result['result'] = {}
            result['result']['issue_type'] = "unknown error"
            result['result']['issue_message'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""
            result['result']['task_id'] = task_id

        return json.dumps(result)

    def archiver_controller_run(self, publisher_id=None, package_id=None):

        context = {
            'model': model,
            'session': model.Session,
            'site_url': config.get('ckan.site_url'),
            'user': config.get('iati.admin_user.name'),
            'apikey': config.get('iati.admin_user.api_key'),
            'api_version': 3,
        }
        import ckan.plugins as p
        if not c.user:
            p.toolkit.abort(403, 'Permission denied, only system administrators can run the archiver.')

        self.is_sysadmin = authz.is_sysadmin(c.user)

        if not self.is_sysadmin:
            # User does not have permissions on any publisher
            p.toolkit.abort(403, 'Permission denied, only system administrators can run the archiver.')

        tasks = []
        pkg_stat = {}
       
        if package_id:
            package_ids = [package_id]
        elif publisher_id:
            try:

                org = toolkit.get_action('organization_show')(context, {'id': publisher_id, 'include_datasets': True})

            except toolkit.ObjectNotFound:

                pkg_stat['status'] = "Error"
                pkg_stat['message'] = 'Could not find Publisher: {0}'.format(publisher_id)
                return pkg_stat

            package_ids = [p['name'] for p in org['packages']]
        else:
            try:
                package_ids = toolkit.get_action('package_list')(context, {})
            except toolkit.ObjectNotFound:
                pkg_stat['status'] = "Error"
                pkg_stat['message'] = 'Could not find Publisher: {0}'.format(publisher_id)
                return pkg_stat

        for index, pkg_id in enumerate(package_ids):
            task = OrderedDict()

            job = jobs.enqueue(arch.run, [pkg_id, None, publisher_id])

            task['task_id'] = job.id
            task['name'] = pkg_id
            task['status'] = 'Queued'
            if publisher_id:
                task['title'] = org['packages'][index]['title']
            else:
                pkg = toolkit.get_action('package_show')(context, {'id': pkg_id})
                task['title'] = pkg['title']
            tasks.append(json.dumps(task))
        pkg_stat['status'] = "success"
        pkg_stat['message'] = "All jobs are initiated successfully"
        pkg_stat['tasks'] = tasks
        if publisher_id:
            pkg_stat['id'] = publisher_id
        else:
            pkg_stat['id'] = pkg_id

        if publisher_id:
            pkg_stat['from_publisher'] = True

        if publisher_id:
            return render('user/archiver_result.html', extra_vars=pkg_stat)
        else:
            return render('user/archiver_result.html', extra_vars=pkg_stat)

