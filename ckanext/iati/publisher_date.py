from ckanapi import LocalCKAN, NotAuthorized, errors
from dateutil.parser import parse as date_parse
import logging

log = logging.getLogger(__name__)


class UpdateFirstPublishedDate:

    """
        Daily job that checks for publisher first published date if it is empty.
        Patch the date of first public resource/package date
    """

    def __init__(self, username):
        self.iati = LocalCKAN(username=username)

    def _get_organization_list(self):
        """
        API action to get the list of active organizations
        :return: list of organizations
        """
        print("Obtaining the list of all organizations...")
        _organization_list = 'organization_list'
        return self.iati.call_action(_organization_list)

    def _organization_show(self, org_name):
        """
        Gets the organization metadata to check if the date exists
        :param org_name: Name of the organization
        :return: Metadata of the organizations - python dictionary
        """
        _organization_show = 'organization_show'

        return self.iati.call_action(_organization_show, {'id': org_name})

    def _get_date(self, org_name):
        """
        This to get the first published date from the package if the date is missing
        :param org_name: Organization name (where first published date is empty)
        :return: first published date (i.e. package published date for the first  time)
        """
        dates = []

        data_dict = {
            'fq': 'organization:{}'.format(org_name.strip()),
            'rows': 100
        }

        package_search_results = self.iati.call_action('package_search', data_dict)['results']

        if len(package_search_results) == 0:
            return ''

        for package in package_search_results:
            try:
                # Make sure package is not private
                if (not package['private']) or (str(package['private']).strip() != "false"):
                    resource_created_date = package['resources'][0]['created']
                    dates.append(resource_created_date)
            except Exception as e:
                print("Error occured while searching for package or resources: {}".format(str(e)))
                continue

        if len(dates) == 0:
            return ''

        date_string = str(sorted([date_parse(x) for x in dates])[0].date().strftime('%d.%m.%Y'))

        return date_string

    def _patch_organization(self, data_dict):
        """
        Patch the organization metadata
        :param data_dict: dictionary containing {'publisher_first_publish_date': 'xxx'}
        :return: None - patch the IATI registry organization metadata
        """

        patch_organization = 'organization_patch'

        try:
            self.iati.call_action(patch_organization, data_dict)
            print("Patched date successfully....")
        except Exception as e:
            print("Error occured while patching date: {}".format(str(e)))
            pass

    def update_organization(self):

        """
        Function that combines all methods - get, show, package
        :return: Nothing (patches the IATI registry organization metadata
        """

        org_list = self._get_organization_list()

        for org in org_list:
            print("Checking for organization: {}".format(str(org)))
            try:
                _org_data = self._organization_show(org)

                # Checks for publisher_first_publish_date key and empty value
                if not _org_data.get('publisher_first_publish_date', ''):
                    print("Published date is empty: {}".format(str(org)))
                    pub_dt = self._get_date(_org_data['name'])
                    print("Published date: {}".format(str(pub_dt)))
                    if pub_dt:
                        data_dict = dict()
                        data_dict['id'] = _org_data['id']
                        data_dict['publisher_first_publish_date'] = str(pub_dt)
                        print("Patching date: {}".format(str(pub_dt)))
                        self._patch_organization(data_dict)
                    else:
                        print("Empty publisher date - not published: {}".format(str(org)))

            except errors.NotFound:
                print("Organization Not found: {}".format(str(org)))
                pass

            except Exception as e:
                print("Unhandled error occurred: {}".format(str(e)))
                pass


def run():
    username = 'admin'
    execute_date = UpdateFirstPublishedDate(username)
    execute_date.update_organization()
