from ckan.lib.base import render, BaseController
from ckan.common import c
import ckan.logic as logic
import ckan.model as model

class PublisherController(BaseController):

    def members_read(self, id):
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}

        try:
            c.members = logic.get_action('member_list')(
                context, {'id': id, 'object_type': 'user'}
            )
            print(c.members)
            c.group_dict = logic.get_action('organization_show')(context, {'id': id})
        except logic.NotAuthorized:
            abort(401, _('Unauthorized to read group members %s') % '')
        except logic.NotFound:
            abort(404, _('Group not found'))
        return render('organization/members_read.html')
