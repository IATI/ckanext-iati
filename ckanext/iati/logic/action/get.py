from ckan.logic.action.get import package_show as package_show_core
from ckan.logic.action.get import package_show_rest as package_show_rest_core

def package_show(context, data_dict):

    package_dict = package_show_core(context, data_dict)
    group = context['package'].groups[0] if len(context['package'].groups) else None
    if group:
        new_extras = [
            {'key': 'publishertype', 'value': group.extras.get('type', '')},
            {'key': 'publisher_organization_type', 'value': group.extras.get('publisher_organization_type', '')},
            {'key': 'publisher_country', 'value': group.extras.get('publisher_country', '')},
            {'key': 'publisher_iati_id', 'value': group.extras.get('publisher_iati_id', '')},
        ]
    
    package_dict['extras'].extend(new_extras)

    return package_dict

def package_show_rest(context, data_dict):

    package_dict = package_show_rest_core(context, data_dict)

    group = context['package'].groups[0] if len(context['package'].groups) else None
    if group:
        new_extras = {
            'publishertype':group.extras.get('type', ''),
            'publisher_organization_type':group.extras.get('publisher_organization_type', ''),
            'publisher_country':group.extras.get('publisher_country', ''),
            'publisher_iati_id':group.extras.get('publisher_iati_id', ''),
        }

    package_dict['extras'].update(new_extras)

    return package_dict

