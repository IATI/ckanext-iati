from flask import Blueprint, make_response
import ckan.lib.base as base
import ckan.plugins as p
import ckan.model as model
import ckan.logic as logic
import ckan.lib.helpers as h
from ckan.common import c, _, request, config
import logging

log = logging.getLogger(__file__)

ValidationError = logic.ValidationError
NotAuthorized = logic.NotAuthorized

users = Blueprint('users', __name__, url_prefix='/user')


def delete_selected_users():
    context = {'model': model,
               'user': c.user, 'auth_user_obj': c.userobj}
    try:
        logic.check_access('sysadmin', context, {})
    except logic.NotAuthorized:
        base.abort(403, _('Need to be system administrator to administer'))

    selected_user_ids = request.form.getlist('selected_users')
    deleted_users = []
    for user_id in selected_user_ids:
        try:
            p.toolkit.check_access('user_delete', context, {})
            user = p.toolkit.get_action('user_show')(context, {'id': user_id})
            p.toolkit.get_action('user_delete')(context, {'id': user_id})
            deleted_users.append(user['name'])
        except Exception as e:
            log.error(f"Error deleting user with ID {user_id}: {str(e)}")
            return False
    extra_vars = {
        'deleted_users': deleted_users
    }
    return base.render('user/delete.html', extra_vars)
    # return deleted_users


users.add_url_rule('/delete_selected_users', view_func=delete_selected_users, methods=['POST'])