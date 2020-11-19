from flask import Blueprint
from ckan.views import group as publisher
import ckan.plugins as p
import ckan.lib.helpers as h
import ckan.model as model
import ckan.logic as logic
from ckan.common import c, _, request, config

publisher_blueprint = Blueprint(u'publisher', __name__,
                                url_prefix=u'/publisher',
                                url_defaults={u'group_type': u'organization',
                                              u'is_organization': True})


def members_read(id):
    context = {'model': model, 'session': model.Session,
               'user': c.user or c.author}
    extra_vars = {}
    try:
        c.members = logic.get_action('member_list')(
            context, {'id': id, 'object_type': 'user'}
        )
        c.group_dict = logic.get_action('organization_show')(context, {'id': id})
        extra_vars.update({'group_type': c.group_dict.get('type', '')})
    except logic.NotAuthorized:
        p.toolkit.abort(401, _('Unauthorized to read group members %s') % '')
    except logic.NotFound:
        p.toolkit.abort(404, _('Group not found'))
    return render('organization/members_read.html', extra_vars=extra_vars)


def register_group_plugin_rules(blueprint):
    actions = [
        u'member_delete', u'history', u'followers', u'follow',
        u'unfollow', u'admins', u'activity'
    ]
    blueprint.add_url_rule(u'/', view_func=publisher.index, strict_slashes=False)
    blueprint.add_url_rule(
        u'/new',
        methods=[u'GET', u'POST'],
        view_func=publisher.CreateGroupView.as_view(str(u'new')))
    blueprint.add_url_rule(u'/<id>', methods=[u'GET'], view_func=publisher.read)
    blueprint.add_url_rule(
        u'/edit/<id>', view_func=publisher.EditGroupView.as_view(str(u'edit')))
    blueprint.add_url_rule(
        u'/activity/<id>/<int:offset>', methods=[u'GET'], view_func=publisher.activity)
    blueprint.add_url_rule(u'/about/<id>', methods=[u'GET'], view_func=publisher.about)
    blueprint.add_url_rule(
        u'/members/<id>', methods=[u'GET', u'POST'], view_func=publisher.members)
    blueprint.add_url_rule(
        u'/member_new/<id>',
        view_func=publisher.MembersGroupView.as_view(str(u'member_new')))
    blueprint.add_url_rule(
        u'/bulk_process/<id>',
        view_func=publisher.BulkProcessView.as_view(str(u'bulk_process')))
    blueprint.add_url_rule(
        u'/delete/<id>',
        methods=[u'GET', u'POST'],
        view_func=publisher.DeleteGroupView.as_view(str(u'delete')))
    for action in actions:
        blueprint.add_url_rule(
            u'/{0}/<id>'.format(action),
            methods=[u'GET', u'POST'],
            view_func=getattr(publisher, action))

    blueprint.add_url_rule(
        u'/members/<id>',
        methods=[u'GET'],
        view_func=members_read)

register_group_plugin_rules(publisher_blueprint)
