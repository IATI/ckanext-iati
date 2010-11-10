import os 
try:
    import json
except ImportError:
    import simplejson as json
from ckan.config.middleware import make_app
from paste.fixture import TestApp
from ckan.lib.cli import CkanCommand
from ckan import model

import urllib

import paste.fixture

from ckanclient import CkanClient, Request

class ClientError(Exception):
    pass

class WsgiCkanClient(CkanClient):
    '''Same as CkanClient, but instead of requests going through urllib,
    they are passed directly to an application\'s Paste (webtest/wsgi)
    interface.'''
    def __init__(self, app, **kwargs):
        self.app = app
        super(WsgiCkanClient, self).__init__(**kwargs)

    def open_url(self, location, data=None, headers={}, method=None):
        if self.is_verbose:
            self._print("ckanclient: Opening %s" % location)
        self.last_location = location

        if data != None:
            data = urllib.urlencode({data: 1})
        # Don't use request beyond getting the method
        req = Request(location, data, headers, method=method)

        # Make header values ascii strings
        for key, value in headers.items():
            headers[key] = str('%s' % value)

        method = req.get_method()
        kwargs = {'status':'*', 'headers':headers, 'extra_environ': {'REMOTE_USER': "iati-import"}}
        try:
            if method == 'GET':
                assert not data
                res = self.app.get(location, **kwargs)
            elif method == 'POST':
                res = self.app.post(location, data, **kwargs)
            elif method == 'PUT':
                res = self.app.put(location, data, **kwargs)
            elif method == 'DELETE':
                assert not data
                res = self.app.delete(location, **kwargs)
            else:
                raise ClientError('No Paste interface for method \'%s\': %s' % \
                                  (method, location))
        except paste.fixture.AppError, inst:
            self._print("ckanclient: error: %s" % inst)
            self.last_http_error = inst
            self.last_status = 500
            self.last_message = repr(inst.args)
        else:
            if res.status != 200:
                self._print("ckanclient: Received HTTP error code from CKAN resource.")
                self._print("ckanclient: location: %s" % location)
                self._print("ckanclient: response code: %s" % res.status)
                self._print("ckanclient: request headers: %s" % headers)
                self._print("ckanclient: request data: %s" % data)
                self._print("ckanclient: error: %s" % res)
                self.last_http_error = res
                self.last_status = res.status
                self.last_message = res.body
            else:
                self._print("ckanclient: OK opening CKAN resource: %s" % location)
                self.last_status = res.status
                self._print('ckanclient: last status %s' % self.last_status)
                self.last_body = res.body
                self._print('ckanclient: last body %s' % self.last_body)
                self.last_headers = dict(res.headers)
                self._print('ckanclient: last headers %s' % self.last_headers)
                content_type = self.last_headers['Content-Type']
                self._print('ckanclient: content type: %s' % content_type)
                is_json_response = False
                if 'json' in content_type:
                    is_json_response = True
                if is_json_response:
                    self.last_message = self._loadstr(self.last_body)
                else:
                    self.last_message = self.last_body
                self._print('ckanclient: last message %s' % self.last_message)

        



FIXTURES_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'fixtures.json')

class CreateIatiFixtures(CkanCommand):
    '''Create IATI fixture data in the database.
    '''
    group_name = 'iati'
    summary = __doc__.split('\n')[0]
    usage = __doc__
    max_args = 1
    min_args = 0
    
    def _load_app(self):
        from paste.deploy import appconfig
        if not self.options.config:
            msg = 'No config file supplied'
            raise self.BadCommand(msg)
        self.filename = os.path.abspath(self.options.config)
        try:
            fileConfig(self.filename)
        except Exception: pass
        conf = appconfig('config:' + self.filename)
        self.app = make_app(conf.global_conf, **conf.local_conf)
    
    def command(self):
        self._load_app()
        
        fp = open(FIXTURES_PATH, 'r')
        fixtures = json.load(fp)
        fp.close()
        
        user_name = u"iati-import"
        user = model.User.by_name(user_name)
        if user is None:
            user = model.User(name=user_name, fullname=u"IATI Fixtures Importer")
            model.add_user_to_role(user, model.Role.ADMIN, model.System())
            model.Session.add(user)
            model.repo.commit_and_remove()
            user = model.User.by_name(user_name)
        
        app = TestApp(self.app)
        client = WsgiCkanClient(app, api_key=user.apikey)
           
        for fixture in fixtures.get('groups'):
            existing = client.group_entity_get(fixture.get('name'))
            if isinstance(existing, dict): 
                client.group_entity_put(fixture)
            else:
                client.group_register_post(fixture)
            assert client.last_status == 200, client.last_message
        
        for fixture in fixtures.get('packages'):
            existing = client.package_entity_get(fixture.get('name'))
            if isinstance(existing, dict): 
                client.package_entity_put(fixture)
            else:
                client.package_register_post(fixture)
            assert client.last_status == 200, client.last_message
         
        