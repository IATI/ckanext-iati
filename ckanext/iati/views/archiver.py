from flask import Blueprint
from flask.views import MethodView
from ckan.common import _, c, g, config
from ckan.lib.base import render, abort
import ckan.plugins as p
import ckan.logic as logic
import ckan.model as model
import ckan.authz as authz
import ckan.lib.jobs as jobs
from ckanext.iati import archiver as arch
from collections import OrderedDict
import json
import logging

log = logging.getLogger(__name__)
ValidationError = logic.ValidationError
NotAuthorized = logic.NotAuthorized
NotFound = logic.NotFound

archiver = Blueprint(u'archiver', __name__, url_prefix=u'/archiver')


class ArchiverViewRun(MethodView):

    @staticmethod
    def render_template(view_type, extras):

        if view_type == "publisher":
            return render('organization/archiver.html', extra_vars=extras)
        else:
            return render('user/archiver.html', extra_vars=extras)

    @staticmethod
    def run_archiver_after_package_create_update(package_id):
        """
        Run archiver after package update or package create.

        Note: There is no access control here. Be careful on where this is called from. This is the fix for
        Issue: https://github.com/IATI/ckanext-iati/issues/270

        :param package_id: str
        :return: None
        """

        if not package_id:
            log.error("No package id available. Cannot run the archiver.")
            return None

        job = jobs.enqueue(arch.run, [package_id, None, None])
        log.info("Triggered background job for package: {}".format(package_id))
        log.info("Job id: {}".format(job.id))

        return None

    @staticmethod
    def status(task_id=None):

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
                result['result'][
                    'issue_message'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""
                result['result']['task_id'] = task_id

        else:
            result.update({'status': 'failed'})
            result['result'] = {}
            result['result']['issue_type'] = "unknown error"
            result['result'][
                'issue_message'] = "Something went wrong, please try again or contact support quoting the error \"Background job was not created\""
            result['result']['task_id'] = task_id

        return json.dumps(result)

    def get(self, view_type, id):
        """
        Archiver view for publisher and dataset
        :param view_type:
        :param id:
        :return:
        """

        context = {u'model': model, u'session': model.Session, u'user': c.user or c.author}
        extra_vars = dict()

        try:
            logic.check_access('sysadmin', context, {})
        except NotAuthorized:
            abort(403, _('Need to be system administrator to administer'))

        if view_type == "publisher":
            try:
                group_dict = p.toolkit.get_action(u'organization_show')(context, {u'id': id})
                group_type = group_dict[u'type']
                g.group_dict = group_dict
                extra_vars[u"group_type"] = group_type
                extra_vars[u"group_dict"] = group_dict
                return self.render_template(view_type, extra_vars)
            except (NotFound, NotAuthorized):
                abort(404, _(u'Group not found'))
        elif view_type == "status":
            return self.status(id)
        else:
            extra_vars[u'id'] = id
            try:
                pkg = p.toolkit.get_action(u'package_show')(context, {u'id': id})
                extra_vars[u'organization'] = pkg[u'organization']
                extra_vars[u'pkg'] = pkg
                return self.render_template(view_type, extra_vars)
            except (NotFound, NotAuthorized):
                abort(404, _(u'Group not found'))

    def post(self, view_type, id):
        """

        :param view_type:
        :param id:
        :return:
        """
        publisher_id = None
        package_id = None
        if view_type == "publisher":
            publisher_id = id
        else:
            package_id = id

        context = {
            u'model': model,
            u'session': model.Session,
            u'site_url': config.get('ckan.site_url'),
            u'user': config.get('iati.admin_user.name'),
            u'apikey': config.get('iati.admin_user.api_key'),
            u'api_version': 3,
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
                org = p.toolkit.get_action('organization_show')(
                    context, {'id': publisher_id, 'include_datasets': False})
                pkg_stat['group_dict'] = org
            except p.toolkit.ObjectNotFound:
                pkg_stat['status'] = "Error"
                pkg_stat['message'] = 'Could not find Publisher: {0}'.format(publisher_id)
                return pkg_stat

            # Assuming max packages for publishers is 1000
            package_ids = p.toolkit.get_action('package_search')(
                context,
                {"fq": "organization:{}".format(org["name"]), 'rows': 1000}
            )["results"]
            
        else:
            try:
                package_ids = p.toolkit.get_action('package_list')(context, {})
            except p.toolkit.ObjectNotFound:
                pkg_stat['status'] = "Error"
                pkg_stat['message'] = 'Could not find Publisher: {0}'.format(publisher_id)
                return pkg_stat

        for index, _pkg in enumerate(package_ids):
            if isinstance(_pkg, dict):
                pkg_id = _pkg['name']
            else:
                pkg_id = _pkg
            task = OrderedDict()

            job = jobs.enqueue(arch.run, [pkg_id, None, publisher_id])

            task[u'task_id'] = job.id
            task[u'name'] = pkg_id
            task[u'status'] = 'Queued'
            if publisher_id:
                task[u'title'] = _pkg[u'title']
            else:
                pkg = p.toolkit.get_action('package_show')(context, {'id': pkg_id})
                task[u'title'] = pkg['title']
                pkg_stat['pkg'] = pkg
            tasks.append(json.dumps(task))

        pkg_stat['status'] = "success"
        pkg_stat['message'] = "All jobs are initiated successfully"
        pkg_stat['tasks'] = tasks
        if publisher_id:
            pkg_stat['id'] = publisher_id
        else:
            pkg_stat['id'] = id

        if publisher_id:
            pkg_stat['from_publisher'] = True

        return render('user/archiver_result.html', extra_vars=pkg_stat)


archiver.add_url_rule(
    u'/<view_type>/<id>',
    view_func=ArchiverViewRun.as_view('archiver_controller'),
    methods=[u'GET', u'POST'])

