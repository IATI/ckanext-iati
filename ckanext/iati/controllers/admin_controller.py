from ckan.controllers.admin import AdminController
import ckan.lib.base as base
import ckan.plugins as p
import ckan.model as model
import ckan.logic as logic
import ckan.lib.helpers as h
from ckanext.iati.logic import validators
import csv
import StringIO
import logging
log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)
ValidationError = logic.ValidationError
NotAuthorized = logic.NotAuthorized

c = base.c
request = base.request
_ = base._


class PurgeController(AdminController):

    """
    Change the core purge controller which is not consistent -
    This is because of the revisions associated with other packages - data inconsistent
    Note: we are not checking any revisions while purge-package. 
    Instead we delete the datasets if it flagged as deleted in database
    """

    def _active_publisher_data(self, from_dt, to_dt):
        """
        Get the active publisher data given from and to date
        :param from_dt:
        :param to_dt:
        :return:
        """
        query = """
        SELECT * FROM (
        SELECT public.group.name, public.group.state, package.id, tb2.data_updated, tb1.package_type, row_number() 
        OVER (PARTITION By public.group.name ORDER BY tb2.data_updated DESC) AS rownum FROM (
        SELECT package_extra.package_id AS ac_pkg_id, package_extra.value AS package_type FROM package_extra 
        WHERE package_extra.key = 'filetype' AND package_extra.value='activity') AS tb1, (
        SELECT package_extra.package_id AS dt_pkg_id, package_extra.value AS data_updated FROM package_extra 
        WHERE package_extra.key = 'data_updated' AND (
        package_extra.value BETWEEN '{}' AND '{}')) AS tb2, package, public.group 
        WHERE tb1.ac_pkg_id = tb2.dt_pkg_id AND tb1.ac_pkg_id = package.id 
        AND package.state='active' 
        AND package.private = 'f' 
        AND public.group.id = package.owner_org) AS gp 
        WHERE gp.rownum=1;""".format(from_dt, to_dt)
        print(query)
        conn = model.Session.connection()
        rows = conn.execute(query)
        active_publishers = [{key: value for (key, value) in row.items()} for row in rows]

        return active_publishers

    def trash(self):
        deleted_revisions = model.Session.query(
            model.Revision).filter_by(state=model.State.DELETED)
        deleted_packages = list(model.Session.query(
            model.Package).filter_by(state=model.State.DELETED))
        msgs = []
        if (u'purge-packages' in request.params) or (
                u'purge-revisions' in request.params):
            if u'purge-packages' in request.params:
                revs_to_purge = []

                pkg_len = len(deleted_packages)

                if pkg_len > 0:
                    for i, pkg in enumerate(deleted_packages, start=1):

                        log.debug('Purging {0}/{1}: {2}'.format(i, pkg_len, pkg.id))
                        members = model.Session.query(model.Member) \
                            .filter(model.Member.table_id == pkg.id) \
                            .filter(model.Member.table_name == 'package')
                        if members.count() > 0:
                            for m in members.all():
                                m.purge()

                        pkg = model.Package.get(pkg.id)
                        model.repo.new_revision()
                        pkg.purge()
                        model.repo.commit_and_remove()
                else:
                    msg = _('No deleted datasets to purge')
                    msgs.append(msg)
            else:
                revs_to_purge = [rev.id for rev in deleted_revisions]
            revs_to_purge = list(set(revs_to_purge))
            for id in revs_to_purge:
                revision = model.Session.query(model.Revision).get(id)
                try:
                    # TODO deleting the head revision corrupts the edit
                    # page Ensure that whatever 'head' pointer is used
                    # gets moved down to the next revision
                    model.repo.purge_revision(revision, leave_record=False)
                except Exception as inst:
                    msg = _(u'Problem purging revision %s: %s') % (id, inst)
                    msgs.append(msg)
            h.flash_success(_(u'Purge complete'))
        else:
            msgs.append(_(u'Action not implemented.'))

        for msg in msgs:
            h.flash_error(msg)
        return h.redirect_to(u'admin.trash')

    def reports(self):
        """
        This is for active publisher reports. Given time period.
        Maximum allowed time period is 24 months
        i.e. approximate 732 days
        :return:
        """
        context = {'model': model,
                   'user': c.user, 'auth_user_obj': c.userobj}
        try:
            logic.check_access('sysadmin', context, {})
        except logic.NotAuthorized:
            base.abort(403, _('Need to be system administrator to administer'))

        data_dict = {}

        vars = {
            "errors": {},
            "error_summary": {},
            "data_dict": {}
        }

        if request.method == "POST":
            _params = request.params

            if "run" in _params:
                try:
                    data_dict['from_dt'] = _params.get('from_dt')
                    data_dict['to_dt'] = _params.get('to_dt')

                    for key in ('from_dt', 'to_dt'):
                        try:
                            validators.validate_date(key, data_dict)
                        except ValueError:
                            raise ValidationError({key: ["Not a valid date"]})

                    _errors = validators.check_date_period(data_dict, vars['errors'])

                    if _errors:
                        raise ValidationError(_errors)

                    pub_data = self._active_publisher_data(data_dict.get('from_dt'), data_dict.get('to_dt'))
                    report_page = h.url_for(controller='ckanext.iati.controllers.admin_controller:PurgeController',
                                            action='reports')
                    if pub_data:
                        # 1st element keys is the header
                        fieldnames = list(pub_data[0].keys())
                        file_object = StringIO.StringIO()
                        writer = csv.DictWriter(file_object, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                        writer.writeheader()

                        for row_dict in pub_data:
                            writer.writerow(row_dict)

                        result = file_object.getvalue()
                        file_object.close()

                        file_name = "active_publisher_from_{}_to_{}".format(
                            data_dict.get('from_dt'), data_dict.get('ro_dt'))
                        p.toolkit.response.headers['Content-type'] = 'text/csv'
                        p.toolkit.response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % str(
                            file_name)

                        h.flash_success(_("Please see the downloaded CSV file. Active Publisher Count: {}".format(
                            len(pub_data))))

                        return result

                    else:
                        h.flash_error(_("No data avaliable for the given dates"))
                        h.redirect_to(report_page)

                except NotAuthorized as e:
                    vars["errors"] = e.error_dict
                    vars["error_summary"] = e.error_summary
                    h.flash_error(_("Not authorized to run this. Only sysadmin can run this."))
                    abort(403, _('Unauthorized to view or run this.'))
                except ValidationError as e:
                    vars["errors"] = e.error_dict
                    vars["error_summary"] = e.error_summary
                    vars['data_dict'] = data_dict
                    h.flash_error(_("Form validation error. Please check the given dates"))

        return base.render('admin/reports.html', extra_vars=vars)
