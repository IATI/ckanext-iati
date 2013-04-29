from ckan.authz import Authorizer

def issues_report_csv(context, data_dict):
    user = context.get('user')
    if not Authorizer().is_sysadmin(user):
        return {'success': False, 'msg': 'Not authorized to see this report'}

    return {'success': True}
