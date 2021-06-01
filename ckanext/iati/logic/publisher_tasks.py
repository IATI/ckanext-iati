from ckan.plugins.toolkit import config
from ckan.lib import jobs
import ckan.model as model
from ckan.plugins.toolkit import get_action
from ckan import logic
import time
import logging

log = logging.getLogger(__name__)


def update_organization_dataset_names(old_org_name, new_org_name, org_id):
    """
    This is used to change all pakcgae names when publisher id is changed. Because IATI
    uses naming convention for dataset which includes publisher id
    :param old_org_name: str
    :param new_org_name: str
    :param new_org_name: str (uuid)
    :return: None
    """
    # Run this after org is updated completely
    time.sleep(30)
    context = {
        'model': model,
        'session': model.Session,
        'site_url': config.get('ckan.site_url'),
        'user': config.get('iati.admin_user.name'),
        'apikey': config.get('iati.admin_user.api_key'),
        'api_version': 3,
        'disable_archiver': True
    }

    _fq = 'owner_org:{}'.format(org_id)
    _org_packages = get_action('package_search')(context, {
        'fq': _fq,
        'rows': 10000,
        'include_private': True
    })

    for pkg in _org_packages.get('results', []):
        # Replace only 1st occurrence
        log.info("Updating the package: {} with private state - {}".format(pkg['id'], str(pkg['private'])))
        log.info("Old org: {}".format(old_org_name))
        log.info("New org: {}".format(new_org_name))
        new_package_name = pkg.get('name', '').replace(old_org_name, new_org_name, 1)
        log.info("New package name: {}".format(new_package_name))
        if pkg.get('name', '') != new_package_name:
            context["disable_archiver"] = True
            try:
                _res = get_action('package_patch')(context, {
                    'id': pkg['id'],
                    'name': new_package_name
                })
            except logic.ValidationError as e:
                log.error(e)
            except Exception as e:
                log.error("Org name change detected but package update failed for some reason")
                log.error(e)
    return None
