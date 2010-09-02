import sys, os
from pprint import pprint
import ckanclient
try:
    import json
except ImportError:
    import simplejson as json

# pudo 2010-09-02 note:
# python ckanext/iati/fixtures.py http://localhost:5000/api 0a6ffc5c-5043-4092-9f5b-901d5046f173

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'fixtures.json')

def load_fixtures_via_api(api_url, api_key):
    cc = ckanclient.CkanClient(base_location=api_url, api_key=api_key)
    fp = open(FIXTURES_PATH, 'r')
    fixtures = json.load(fp)
    fp.close()
    for fixture in fixtures: 
        name = fixture['name'] = fixture.get('name').lower()
        print "Loading %s" % fixture.get('title').encode('utf-8')
        existing = cc.package_entity_get(name)
        if existing: 
            cc.package_entity_put(fixture)
        else:
            cc.package_register_post(fixture)
        #pprint(existing)
        #pprint(fixture) 
        



if __name__ == '__main__':
    if not len(sys.argv) == 3:
        print >>sys.stderr, "Usage: %s <api_url> <api_key>" % sys.argv[0]
        sys.exit(1)
    api_url, api_key = sys.argv[1], sys.argv[2]
    load_fixtures_via_api(api_url, api_key)