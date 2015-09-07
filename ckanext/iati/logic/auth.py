import ckan.plugins as p

import ckan.logic.auth.create as create_core
import ckan.logic.auth.update as update_core


def package_create(context, data_dict):

    check = create_core.package_create(context, data_dict)

    if not check['success']:
        return check

    authorized_orgs = p.toolkit.get_action('organization_list_for_user')(context, {})
    if not len(authorized_orgs):
        return {'success': False, 'msg': 'You need to belong to an authorized publisher to create a dataset'}
    return {'success': True}

def package_update(context, data_dict):

    check = update_core.package_update(context, data_dict)

    if not check['success']:
        return check

    authorized_orgs = p.toolkit.get_action('organization_list_for_user')(context, {})
    if not len(authorized_orgs):
        return {'success': False, 'msg': 'You need to belong to an authorized publisher to update a dataset'}
    return {'success': True}

def issues_report_csv(context, data_dict):
    '''
    Everybody can see this report
    '''
    return {'success': True}
