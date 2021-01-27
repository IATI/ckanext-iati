from flask import Blueprint
from ckan.views import group as publisher
import ckan.plugins as p
import ckan.lib.helpers as h
import ckan.model as model
import ckan.logic as logic
from ckan.common import c, g, _, request, config
from ckan.lib.base import render
import ckan.lib.base as base
import ckan.lib.navl.dictization_functions as dict_fns
from ckanext.iati.logic.csv_action import PublishersListDownload

NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized
ValidationError = logic.ValidationError
tuplize_dict = logic.tuplize_dict
clean_dict = logic.clean_dict
parse_params = logic.parse_params

publisher_blueprint = Blueprint(u'publisher', __name__,
                                url_prefix=u'/publisher',
                                url_defaults={u'group_type': u'organization',
                                              u'is_organization': True})


def members_read(id, group_type, is_organization):
    group_type = u'organization'
    context = {u'model': model, u'session': model.Session,
               u'user': c.user or c.author}
    try:
        data_dict = {u'id': id}
        logic.check_access(u'group_edit_permissions', context, data_dict)
        members = p.toolkit.get_action(u'member_list')(context, {
            u'id': id,
            u'object_type': u'user'
        })
        data_dict[u'include_datasets'] = False
        group_dict = p.toolkit.get_action(u'organization_show')(context, data_dict)
    except logic.NotAuthorized:
        p.toolkit.abort(401, _(u'Unauthorized to read/edit group members %s') % '')
    except logic.NotFound:
        p.toolkit.abort(404, _(u'Group not found'))

    g.members = members
    g.group_dict = group_dict

    extra_vars = {
        u"members": members,
        u"group_dict": group_dict,
        u"group_type": group_type
    }
    return render('organization/members_read.html', extra_vars)


def publisher_list_download(output_format, group_type, is_organization):
    publisher_downloader = PublishersListDownload(output_format)
    output = publisher_downloader.download()
    return output


class MembersGroupViewPatch(publisher.MembersGroupView):
    """
    This is the patch to solve the core ckan bug where action user_invite error is not captured.
    """

    def post(self, group_type, is_organization, id=None):
        publisher.set_org(is_organization)
        context = self._prepare(id)
        data_dict = clean_dict(
            dict_fns.unflatten(tuplize_dict(parse_params(request.form))))
        data_dict['id'] = id

        email = data_dict.get(u'email')

        if email:
            user_data_dict = {
                u'email': email,
                u'group_id': data_dict['id'],
                u'role': data_dict['role']
            }
            del data_dict['email']
            try:
                user_dict = publisher._action(u'user_invite')(context, user_data_dict)
                data_dict['username'] = user_dict['name']
            except NotFound:
                base.abort(404, _(u'Group not found'))
            except ValidationError as e:
                h.flash_error(e.error_summary)
                return h.redirect_to(u'{}.member_new'.format(group_type), id=id)

        try:
            group_dict = publisher._action(u'group_member_create')(context, data_dict)
        except NotAuthorized:
            base.abort(403, _(u'Unauthorized to add member to group %s') % u'')
        except NotFound:
            base.abort(404, _(u'Group not found'))
        except ValidationError as e:
            h.flash_error(e.error_summary)
            return h.redirect_to(u'{}.member_new'.format(group_type), id=id)

        # TODO: Remove
        g.group_dict = group_dict

        return h.redirect_to(u'{}.members'.format(group_type), id=id)


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
        u'/edit_members/<id>', methods=[u'GET', u'POST'], view_func=publisher.members)
    blueprint.add_url_rule(
        u'/member_new/<id>',
        view_func=MembersGroupViewPatch.as_view(str(u'member_new')))
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

    blueprint.add_url_rule(u'/members/<id>', methods=[u'GET'], view_func=members_read)
    blueprint.add_url_rule(u'/download/<output_format>', methods=[u'GET'], view_func=publisher_list_download)


register_group_plugin_rules(publisher_blueprint)
