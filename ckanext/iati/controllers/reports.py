from ckan.lib.base import c, request, response, abort, BaseController

from ckan import model
from ckan import logic


class ReportsController(BaseController):

    def issues_report(self):

        context = {
            'model': model,
            'session':model.Session,
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
