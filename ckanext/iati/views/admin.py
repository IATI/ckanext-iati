import csv
import StringIO
import os
import json
from datetime import datetime
from flask import Blueprint, make_response
import ckan.lib.base as base
import ckan.plugins as p
import ckan.model as model
import ckan.logic as logic
import ckan.lib.helpers as h
from ckan.common import c, _, request, config
from ckanext.iati.logic import validators
from ckanext.iati.model import IATIRedirects
from ckanext.iati.controllers.publisher_list_download import PublishersListDownload
import logging

log = logging.getLogger(__file__)

ValidationError = logic.ValidationError
NotAuthorized = logic.NotAuthorized

admin_tabs = Blueprint(u'admin_tabs', __name__, url_prefix=u'/ckan-admin')


_query = """
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
    WHERE gp.rownum=1;"""


def _active_publisher_data(from_dt, to_dt):
    """
    Get the active publisher data given from and to date
    :param from_dt:
    :param to_dt:
    :return:
    """
    query = _query.format(from_dt, to_dt)
    print(query)
    conn = model.Session.connection()
    rows = conn.execute(query)
    active_publishers = [{key: value for (key, value) in row.items()} for row in rows]

    return active_publishers


def admin_publishers_report():
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
        _params = request.form

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

                pub_data = _active_publisher_data(data_dict.get('from_dt'), data_dict.get('to_dt'))
                report_page = h.url_for('admin_tabs.admin_publishers_report')
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

                    response = make_response(result)
                    response.headers = {
                        "Content-type": 'text/csv',
                        'Content-disposition': 'attachment;filename=%s.csv' % str(file_name)
                    }

                    h.flash_success(_("Please see the downloaded CSV file. Active Publisher Count: {}".format(
                        len(pub_data))))

                    return response

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

    return base.render('admin/reports.html', vars)


def iati_redirects():
    """
    This will map the old and new publisher redirects. For IATI registry
    :return:
    """

    context = {'model': model,
               'user': c.user, 'auth_user_obj': c.userobj}
    try:
        logic.check_access('sysadmin', context, {})
    except logic.NotAuthorized:
        base.abort(403, _('Need to be system administrator to administer'))

    if request.method == "POST":
        if "run" in request.form:
            try:
                IATIRedirects.update_redirects()
                h.flash_success("Updated redirects successfully. "
                                "Please contact support team to restart IATI registry.")
            except Exception as e:
                log.error(e)
                h.flash_error("Something wrong while extracting publisher mapping. Contact support team")
                pass
            h.redirect_to('admin_tabs.iati_redirects')
        else:
            h.flash_error("This should not occur.")

    try:
        redirect_contents, last_updated = IATIRedirects.get_redirects_to_view()
    except Exception as e:
        log.error(e)
        last_updated = "Not Available"
        redirect_contents = dict()

    vars = {
        "redirect_contents": redirect_contents,
        "last_updated": last_updated
    }

    return base.render('admin/redirects.html', vars)


admin_tabs.add_url_rule(u'/iati-redirects', view_func=iati_redirects, methods=['POST', 'GET'])
admin_tabs.add_url_rule(u'/admin-publishers-report', view_func=admin_publishers_report, methods=['POST', 'GET'])


