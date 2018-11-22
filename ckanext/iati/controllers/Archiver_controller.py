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

                        print("*****************************status***********************************", job.result)
                        #data = json.loads(job.result)

                        #result['result']['added'] = data['added']
                        #result['result']['updated'] = data['updated']
                        #result['result']['errors'] = data['errors']
                        #result['result']['warnings'] = data['warnings']

                    except Exception as e:

                        result.update({'status': "failed"})
                        result['result'] = {}
                        result['result']['errors'] = "Something went wrong, please try again or contact support."

            except Exception as e:
                result.update({'status': "failed"})
                result['result'] = {}
                result['result']['errors'] = "Something went wrong 1, please try again or contact support quoting the error \"Background job was not created\""

        else:
            result.update({'status': 'failed'})
            result['result'] = {}
            result['result']['errors'] = "Something went wrong 2, please try again or contact support quoting the error \"Background job was not created\""

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

        for index, package_id in enumerate(package_ids):
            task = OrderedDict()
            job = jobs.enqueue(arch.run, [package_id, publisher_id])
            task[u'task_id'] = job.id
            task[u'name'] = package_id
            task[u'status'] = 'Queued'
            task[u'title'] = org['packages'][index-1]['title']
            tasks.append(json.dumps(task))
        pkg_stat['status'] = "success"
        pkg_stat['message'] = "All jobs are initiated successfully"
        pkg_stat['tasks'] = tasks
        pkg_stat['id'] = publisher_id
        #context = {'model': model, 'session': model.Session,
                   #'user': c.user or c.author}
        #c.group_dict = logic.get_action('organization_show')(context, {'id': id})

        return render('user/archiver_result.html', extra_vars=pkg_stat)

