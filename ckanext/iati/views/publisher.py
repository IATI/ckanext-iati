import logging
import os
import requests

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
import ckan.lib.uploader as uploader
import ckan.lib.navl.dictization_functions as dict_fns
from ckanext.iati.logic.csv_action import PublishersListDownload
import copy

NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized
ValidationError = logic.ValidationError
tuplize_dict = logic.tuplize_dict
clean_dict = logic.clean_dict
parse_params = logic.parse_params

publisher_blueprint = Blueprint('publisher', __name__,
                                url_prefix='/publisher',
                                url_defaults={'group_type': 'organization',
                                              'is_organization': True})

publisher_with_user_blueprint = Blueprint('publisher_with_user', __name__,
                                          url_prefix='/register_publisher',
                                          url_defaults={'group_type': 'organization',
                                                        'is_organization': True})


def members_read(id, group_type, is_organization):
    group_type = 'organization'
    context = {'model': model, 'session': model.Session,
               'user': c.user or c.author}
    try:
        data_dict = {'id': id}
        logic.check_access('group_edit_permissions', context, data_dict)
        members = p.toolkit.get_action('member_list')(context, {
            'id': id,
            'object_type': 'user'
        })
        data_dict['include_datasets'] = False
        group_dict = p.toolkit.get_action('organization_show')(context, data_dict)
    except logic.NotAuthorized:
        p.toolkit.abort(401, _('Unauthorized to read/edit group members %s') % '')
    except logic.NotFound:
        p.toolkit.abort(404, _('Group not found'))

    g.members = members
    g.group_dict = group_dict

    extra_vars = {
        "members": members,
        "group_dict": group_dict,
        "group_type": group_type
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

        email = data_dict.get('email')

        if email:
            user_data_dict = {
                'email': email,
                'group_id': data_dict['id'],
                'role': data_dict['role']
            }
            del data_dict['email']
            try:
                user_dict = publisher._action('user_invite')(context, user_data_dict)
                data_dict['username'] = user_dict['name']
            except NotFound:
                base.abort(404, _('Group not found'))
            except ValidationError as e:
                h.flash_error(e.error_summary)
                return h.redirect_to('{}.member_new'.format(group_type), id=id)

        try:
            group_dict = publisher._action('group_member_create')(context, data_dict)
        except NotAuthorized:
            base.abort(403, _('Unauthorized to add member to group %s') % '')
        except NotFound:
            base.abort(404, _('Group not found'))
        except ValidationError as e:
            h.flash_error(e.error_summary)
            return h.redirect_to('{}.member_new'.format(group_type), id=id)

        # TODO: Remove
        g.group_dict = group_dict

        return h.redirect_to('publisher.members', id=id)


class PublisherCreateWithUserView(publisher.CreateGroupView):

    @staticmethod
    def get_context():
        context = {
            'model': model,
            'session': model.Session
        }
        return context

    @staticmethod
    def resolve_form_field_name_conflict(data, items_to_replace_dict):
        for key in items_to_replace_dict:
            if key in data:
                data[items_to_replace_dict[key]] = data.pop(key)
        return data

    @staticmethod
    def validate_user_create(data_dict, context):

        is_password_mismatch = False
        _schema = schema.default_user_schema()
        session = context['session']
        data = data_dict.copy()
        data = PublisherCreateWithUserView.resolve_form_field_name_conflict(data, {
            "user_name": "name",
            "user_image_url": "image_url",
            "user_image_upload": "image_upload"
        })

        if data['password1'] == data['password2']:
            data['password'] = data['password1']
        else:
            is_password_mismatch = True

        data, errors = dict_fns.validate(data, _schema, context)
        session.rollback()

        if errors:
            if is_password_mismatch:
                errors['password'] = ['Password and confirm password are not same']
            return errors

        return dict()

    @staticmethod
    def validate_publisher_create(data_dict, context):

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

        return dict()

    @staticmethod
    def create_user(data_dict, context):
        data = data_dict.copy()
        data = PublisherCreateWithUserView.resolve_form_field_name_conflict(data, {
            "user_name": "name",
            "user_image_url": "image_url",
            "user_image_upload": "image_upload"
        })
        data['password'] = data['password1']
        return logic.get_action('user_create')(context, data)

    @staticmethod
    def create_publisher(data_dict, context, user_dict):
        data_dict['users'] = [{'name': user_dict['name'], 'capacity': 'admin'}]
        context['user'] = user_dict['name']
        context['auth_user_obj'] = model.User.get(user_dict['id'])
        return logic.get_action('organization_create')(context, data_dict)

    def post(self, group_type, is_organization):
        if g.user:
            # #1799 Don't offer the publisher registration form if already logged in
            return base.render('user/logout_first.html', {})

        is_organization = True
        context = self.get_context()
        try:
            data_dict = clean_dict(
                dict_fns.unflatten(tuplize_dict(parse_params(request.form))))
            data_dict.update(clean_dict(
                dict_fns.unflatten(tuplize_dict(parse_params(request.files)))
            ))
        except dict_fns.DataError:
            base.abort(400, _('Integrity Error'))

        context['message'] = data_dict.get('log_message', '')
        data_dict['type'] = 'organization'

        captcha_response = data_dict['h-captcha-response']
        try:
            response = requests.post('https://hcaptcha.com/siteverify', timeout=20, data={
                'secret': os.environ.get('hCAPTCHA_SECRET_KEY'),
                'response': captcha_response,
            })
            if not response.json().get('success', False):
                error_msg = _(u'Complete captcha to continue. Please try again.')
                h.flash_error(error_msg)
                return self.get(group_type, is_organization, data=data_dict)
        except requests.RequestException as e:
            error_msg = _(u'Error while verifying captcha. Please try again.')
            h.flash_error(error_msg)
            return self.get(group_type, is_organization, data=data_dict)

        # Check for any errors in the data - we need to mimic this as transaction
        user_errors = PublisherCreateWithUserView.validate_user_create(data_dict, context)
        errors = PublisherCreateWithUserView.validate_publisher_create(data_dict, context)
        user_errors = PublisherCreateWithUserView.resolve_form_field_name_conflict(user_errors, {
            "name": "user_name",
            "image_url": "user_image_url",
            "image_upload": "user_image_upload"
        })
        errors.update(user_errors)

        # Check for any errors else create user and th8en publisher in one go
        try:
            if errors:
                raise ValidationError(errors)

            user_dict = PublisherCreateWithUserView.create_user(data_dict, context)
            publisher_dict = PublisherCreateWithUserView.create_publisher(data_dict, context, user_dict)
        except ValidationError as e:
            errors = e.error_dict
            error_summary = e.error_summary
            return self.get(group_type, is_organization,
                            data_dict, errors, error_summary)
        except NotAuthorized as e:
            base.abort(404, _('Not authorized to create group or publisher'))

        h.flash_error("Publisher registered and it is pending for approval. Please wait until you "
                      "receive a approval email. Until then you can use IATI portal with "
                      "the username and password you just created")
        return h.redirect_to('user.login')

    def get(self, group_type, is_organization, data=None, errors=None, error_summary=None):
        if g.user:
            # #1799 Don't offer the publisher registration form if already logged in
            return base.render('user/logout_first.html', {})

        publisher.set_org(is_organization)
        context = self.get_context()
        data = data or dict()
        errors = errors or dict()
        error_summary = error_summary or dict()
        extra_vars = {
            'data': data,
            'errors': errors,
            'error_summary': error_summary,
            'action': 'new',
            'is_user_create': True,
            'group_type': group_type,
            'hcaptcha_site_key': os.environ.get('hCAPTCHA_SITE_KEY')
        }
        user_form = base.render('user/new_user_and_publisher_form.html', extra_vars)
        extra_vars["user_form"] = user_form
        publisher._setup_template_variables(
            context, data, group_type=group_type)
        form = base.render(publisher._get_group_template('group_form', group_type), extra_vars)

        g.form = form
        g.user_form = user_form
        extra_vars["form"] = form
        return base.render(publisher._get_group_template('new_template', group_type), extra_vars)


def register_group_plugin_rules(blueprint):
    actions = [
        'member_delete', 'history', 'followers', 'follow',
        'unfollow', 'admins', 'activity'
    ]
    blueprint.add_url_rule('/', view_func=publisher.index, strict_slashes=False)
    blueprint.add_url_rule(
        '/new',
        methods=['GET', 'POST'],
        view_func=publisher.CreateGroupView.as_view(str('new')))
    blueprint.add_url_rule('/<id>', methods=['GET'], view_func=publisher.read)
    blueprint.add_url_rule(
        '/edit/<id>', view_func=publisher.EditGroupView.as_view(str('edit')))
    blueprint.add_url_rule(
        '/activity/<id>/<int:offset>', methods=['GET'], view_func=publisher.activity)
    blueprint.add_url_rule('/about/<id>', methods=['GET'], view_func=publisher.about)
    blueprint.add_url_rule(
        '/edit_members/<id>', methods=['GET', 'POST'], view_func=publisher.members)
    blueprint.add_url_rule(
        '/member_new/<id>',
        view_func=MembersGroupViewPatch.as_view(str('member_new')))
    blueprint.add_url_rule(
        '/bulk_process/<id>',
        view_func=publisher.BulkProcessView.as_view(str('bulk_process')))
    blueprint.add_url_rule(
        '/delete/<id>',
        methods=['GET', 'POST'],
        view_func=publisher.DeleteGroupView.as_view(str('delete')))

    for action in actions:
        blueprint.add_url_rule(
            '/{0}/<id>'.format(action),
            methods=['GET', 'POST'],
            view_func=getattr(publisher, action))

    blueprint.add_url_rule('/members/<id>', methods=['GET'], view_func=members_read)
    blueprint.add_url_rule('/download/<output_format>', methods=['GET'], view_func=publisher_list_download)


register_group_plugin_rules(publisher_blueprint)

publisher_with_user_blueprint.add_url_rule('/', methods=["GET", "POST"],
                                           view_func=PublisherCreateWithUserView.as_view('register_publisher'))
