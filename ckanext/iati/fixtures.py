import os 
try:
    import json
except ImportError:
    import simplejson as json
from ckan.lib.cli import CkanCommand
from ckan.lib.create_test_data import CreateTestData 

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'fixtures.json')

class CreateIatiFixtures(CkanCommand):
    '''Create IATI fixture data in the database.
    '''
    group_name = 'iati'
    summary = __doc__.split('\n')[0]
    usage = __doc__
    max_args = 1
    min_args = 0
    
    def command(self):
        self._load_config()
        #self._setup_app()
        
        fp = open(FIXTURES_PATH, 'r')
        fixtures = json.load(fp)
        fp.close()
        
        from ckan import model 
        user = model.User(name=u"iati-import", fullname=u"IATI Fixtures Importer")
        model.Session.add(user)
        model.repo.commit_and_remove()
        
        