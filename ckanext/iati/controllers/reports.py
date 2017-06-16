from ckan.lib.base import c, g, request, response, render, abort, BaseController
from ckan.common import _
from ckan import model
from ckan import logic

import ckan.lib.helpers as h


NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized


class ReportsController(BaseController):

    def issues_report(self):

        context = {
            'model': model,
            'session': model.Session,
            'user': c.user,
        }
        data_dict = {
            'publisher': request.params.get('publisher', None)
        }

        try:
            result = logic.get_action('issues_report_csv')(context, data_dict)
        except logic.NotAuthorized:
            abort(401, 'Not authorized to see this report')

        with open(result['file'], 'r') as f:
            content = f.read()

        response.headers['Content-Type'] = 'application/csv'
        response.headers['Content-Length'] = len(content)
        response.headers['Content-Disposition'] = 'attachment; filename="iati.issues.csv"'

        return content

    def dashboard_datasets(self):
        """User Dashboard > My Datasets pagination."""
        context = {'for_view': True, 'user': c.user or c.author,
                   'auth_user_obj': c.userobj}
        data_dict = {'user_obj': c.userobj, 'include_datasets': True}

        try:
            user_dict = logic.get_action('user_show')(context, data_dict)
        except NotFound:
            abort(404, _('User not found'))
        except NotAuthorized:
            abort(401, _('Not authorized to see this page'))
        c.user_dict = user_dict

        items_per_page = g.datasets_per_page or 20  # , readme
        page = self._get_page_number(request.params) or 1
        c.page = h.Page(
            collection=user_dict['datasets'],
            page=page,
            url=h.pager_url,
            item_count=len(user_dict['datasets']),
            items_per_page=items_per_page,
        )
        c.page.items = user_dict['datasets']

        return render('user/dashboard_datasets.html')
