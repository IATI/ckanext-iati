from flask import Blueprint
from ckan.views import group as publisher, user as user_view
import ckan.plugins as p
import ckan.lib.plugins as lib_plugins
import ckan.lib.helpers as h
import ckan.model as model
import ckan.logic as logic
from ckan.common import c, g, _, request, config
from ckan.lib.base import render
import ckan.lib.base as base
import ckan.logic.schema as schema
import ckan.lib.navl.dictization_functions as dict_fns
from ckanext.iati.logic.csv_action import PublishersListDownload
import copy

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

publisher_with_user_blueprint = Blueprint(u'publisher_with_user', __name__,
                                          url_prefix=u'/register_publisher',
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

        return h.redirect_to(u'publisher.members', id=id)


class PublisherCreateWithUserView(publisher.CreateGroupView):

    def _get_context(self):
        context = {
            u'model': model,
            u'session': model.Session
        }
        return context

    def _validate_user_data(self, data_dict, context):

        is_password_mismatch = False
        _schema = schema.default_user_schema()
        session = context['session']
        _data = copy.deepcopy(data_dict)
        _data['name'] = data_dict['user_name']

        if _data['password1'] == _data['password2']:
            _data['password'] = _data['password1']
        else:
            is_password_mismatch = True
            
        data, errors = dict_fns.validate(_data, _schema, context)
        session.rollback()
        if errors:
            if is_password_mismatch:
                errors['password'] = [u'Password and confirm password are not same']
            return errors
        return

    def _validate_publisher_data(self, data_dict, context):

        session = context['session']
        group_plugin = lib_plugins.lookup_group_plugin('organization')
        try:
            _schema = group_plugin.form_to_db_schema_options({
                'type': 'create', 'api': 'api_version' in context,
                'context': context})
        except AttributeError:
            _schema = group_plugin.form_to_db_schema()

        data, errors = lib_plugins.plugin_validate(group_plugin, context, data_dict, _schema, 'organization_create')

        session.rollback()
        if errors:
            return errors
        return

    def _create_user(self, data_dict, context):
        data = copy.deepcopy(data_dict)
        data['name'] = data['user_name']
        return logic.get_action(u'user_create')(context, data)

    def _create_publisher(self, data_dict, context, user_dict):
        data_dict['users'] = [{u'name': user_dict['name'], u'capacity': u'admin'}]
        return logic.get_action(u'group_create')(context, data_dict)

    def post(self, group_type, is_organization):

        if g.user:
            # #1799 Don't offer the publisher registration form if already logged in
            return base.render(u'user/logout_first.html', {})

        is_organization = True
        context = self._get_context()
        try:
            data_dict = clean_dict(
                dict_fns.unflatten(tuplize_dict(parse_params(request.form))))
            data_dict.update(clean_dict(
                dict_fns.unflatten(tuplize_dict(parse_params(request.files)))
            ))
        except dict_fns.DataError:
            base.abort(400, _(u'Integrity Error'))

        context['message'] = data_dict.get(u'log_message', u'')
        data_dict['type'] = u'organization'

        user_errors = self._validate_user_data(data_dict, context) or dict()
        errors = self._validate_publisher_data(data_dict, context) or dict()

        try:
            if 'name' in user_errors:
                user_errors['user_name'] = user_errors.pop('name')

            errors.update(user_errors)

            if errors:
                raise ValidationError(errors)

            user_dict = self._create_user(data_dict, context)
            publisher_dict = self._create_publisher(data_dict, context, user_dict)
        except ValidationError as e:
            errors = e.error_dict
            error_summary = e.error_summary
            return self.get(group_type, is_organization,
                            data_dict, errors, error_summary)
        except NotAuthorized as e:
            base.abort(404, _(u'Not authorized to create group or publisher'))

        h.flash_error("Publisher registered and it is pending for approval. Please wait until you "
                      "receive a approval email. Until then you can use IATI portal with "
                      "the username and password you just created")
        return h.redirect_to(u'user.login')

    def get(self, group_type, is_organization, data=None, errors=None, error_summary=None):

        if g.user:
            # #1799 Don't offer the publisher registration form if already logged in
            return base.render(u'user/logout_first.html', {})

        publisher.set_org(is_organization)
        context = self._get_context()
        is_organization = True # Overwrite
        data = data or dict()
        errors = errors or {}
        error_summary = error_summary or {}
        extra_vars = {
            u'data': data,
            u'errors': errors,
            u'error_summary': error_summary,
            u'action': u'new',
            u'is_user_create': True,
            u'group_type': group_type,
        }
        user_form = base.render(u'user/new_user_and_publisher_form.html', extra_vars)
        extra_vars["user_form"] = user_form
        publisher._setup_template_variables(
            context, data, group_type=group_type)
        form = base.render(publisher._get_group_template(u'group_form', group_type), extra_vars)

        # TODO: Remove
        # ckan 2.9: Adding variables that were removed from c object for
        # compatibility with templates in existing extensions
        g.form = form
        g.user_form = user_form
        extra_vars["form"] = form
        return base.render(publisher._get_group_template(u'new_template', group_type), extra_vars)


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

publisher_with_user_blueprint.add_url_rule(u'/', methods=["GET", "POST"],
                                           view_func=PublisherCreateWithUserView.as_view('register_publisher'))
