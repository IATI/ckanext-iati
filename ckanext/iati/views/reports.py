from flask import Blueprint, make_response
from ckan.lib.base import request, render, abort
from ckan.common import _, c, g
from ckan.views.user import _extra_template_variables
from ckan import model
from ckan import logic
import ckan.plugins as p
import ckan.lib.helpers as h
import csv

NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized

issues = Blueprint('issues', __name__, url_prefix='/report')


def issues_report():
    vars = {}

    context = {
        'model': model,
        'session': model.Session,
        'user': c.user,
    }
    data_dict = {
        'publisher': request.params.get('publisher', None),
        'is_download': False
    }

    try:
        result = logic.get_action('issues_report_csv')(context, data_dict)
        vars['authorization'] = 'success'
        vars['issues_content'] = result
        # vars['header'] = header
        return render('user/archiver_report.html', extra_vars=vars)
    except logic.NotAuthorized:
        vars['authorization'] = "fail"
        abort(401, 'Not authorized to see this report')


def download_issues_report():

    context = {
        'model': model,
        'session': model.Session,
        'user': c.user,
    }
    data_dict = {
        'publisher': request.params.get('publisher', None),
        'is_download': True
    }

    try:
        result = logic.get_action('issues_report_csv')(context, data_dict)
        with open(result['file'], 'r') as f:
            content = f.read()

        response = make_response(content)
        response.headers['Content-Type'] = 'application/csv'
        response.headers['Content-Length'] = len(content)
        response.headers['Content-Disposition'] = 'attachment; filename="iati.issues.csv"'

        return response
    except logic.NotAuthorized:
        abort(401, 'Not authorized to see this report')


issues.add_url_rule('/issues', view_func=issues_report)
issues.add_url_rule('/download_issues_report', view_func=download_issues_report)