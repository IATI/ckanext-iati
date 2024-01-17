from ckan.plugins.toolkit import get_action
from ckanext.iati import helpers as h



def user_list(context, data_dict):
    """
    Functionality: User must be bale to login through email id or username
    Wrap the core user list by considering the option for user email
    """
    val = data_dict['id']
    if h.email_validator(val):
        return h.get_user_list_by_email(val)

    return toolkit.get_action('user_list')(context, data_dict)
