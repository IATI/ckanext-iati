import requests

site = 'https://iatiregistry.org'  # no trailing slash
auth = {'X-CKAN-API-Key': '<api key>'}

publishers_call = requests.get(site + '/api/3/action/organization_list',
                               headers=auth)
publisher_list = publishers_call.json()['result']

for publisher in publisher_list:
    pub_dict = {'id': publisher}
    patch_dict = {'id': publisher,
                  'publisher_contact_email': 'Email not found'}
    show = requests.post(site + '/api/3/action/organization_show',
                         headers=auth, json=pub_dict)
    if show.status_code == 200:
        result = show.json()['result']
        publishers_has_email = result.get('publisher_contact_email', None)
        if publishers_has_email is None:
            patch = requests.post(
                site + '/api/3/action/organization_patch', headers=auth, json=patch_dict)
            print patch.json()
