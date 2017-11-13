from ckan.lib.base import render, BaseController
from ckan.common import c
import ckan.logic as logic
import ckan.model as model
import ckan.plugins as p

class PublisherController(BaseController):

    def members_read(self, id):
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}

        try:
            c.members = logic.get_action('member_list')(
                context, {'id': id, 'object_type': 'user'}
            )
            c.group_dict = logic.get_action('organization_show')(context, {'id': id})
        except logic.NotAuthorized:
            p.toolkit.abort(401, p.toolkit._('Unauthorized to read group members %s') % '')
        except logic.NotFound:
            p.toolkit.abort(404, p.toolkit._('Group not found'))
        return render('organization/members_read.html')

    def dashboard_pending_organizations(self):
        context = {'for_view': True, 'user': c.user or c.author, 'auth_user_obj': c.userobj}
        data_dict = {'user_obj': c.userobj}
        return render('user/dashboard_pending_organizations.html')