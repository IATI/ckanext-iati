import sys
import logging
from sqlalchemy import create_engine
from ckan.lib.cli import CkanCommand
from ckanext.iati.custom_archiver import run as run_archiver
from ckanext.iati import publisher_date as pub_date
from ckan.common import config
import json
import os

log = logging.getLogger('iati_archiver')


class Archiver(CkanCommand):
    '''
    Download and save copies of all IATI activity files, extract some metrics
    from them and store them as extras.

    Usage:

        paster iati-archiver update [-p {publisher-id}] [{package-id}]
           - Archive all activity files or just those belonging to a specific
             package or publisher.

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    min_args = 0
    max_args = 2
    pkg_names = []

    def __init__(self, name):
        super(Archiver, self).__init__(name)
        self.parser.add_option('-p', '--publisher', dest='publisher',
                               action='store', default=None, help='Archive '
                               'datasets only from this publisher')

    def command(self):
        '''
        Parse command line arguments and call appropriate method.
        '''
        if not self.args or self.args[0] in ['--help', '-h', 'help']:
            print Archiver.__doc__
            return

        cmd = self.args[0]
        self._load_config()

        if cmd == 'update':
            package_id = unicode(self.args[1]) if len(self.args) > 1 else None
            publisher_id = self.options.publisher
            result = run_archiver(package_id, publisher_id)
            if not result:
                sys.exit(1)
        else:
            log.error('Command {0} not recognized'.format(cmd))


class PurgeCmd(CkanCommand):
    '''Purge deleted datasets.

    Usage:
      iati-purge - remove deleted datasets from db entirely
    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    max_args = 2
    min_args = 0

    def command(self):
        self._load_config()

        if not self.args:
            print(self.usage)
        elif self.args[0] == 'purge':
            self.iati_purge()

    def iati_purge(self):
        '''Purges deleted datasets.'''
        import ckan.model as model

        deleted_packages = list(model.Session.query(
                    model.Package).filter_by(state=model.State.DELETED))
        pkg_len = len(deleted_packages)

        for i, pkg in enumerate(deleted_packages, start=1):

            print('Purging {0}/{1}: {2}'.format(i, pkg_len, pkg.id))
            members = model.Session.query(model.Member) \
                           .filter(model.Member.table_id == pkg.id) \
                           .filter(model.Member.table_name == 'package')
            if members.count() > 0:
                for m in members.all():
                    m.purge()

            pkg = model.Package.get(pkg.id)
            model.repo.new_revision()
            pkg.purge()
            model.repo.commit_and_remove()

        print('Purge complete')


class UpdatePublisherDate(CkanCommand):
    """
        Update first publisher date as cron job or command line.
    """
    summary = __doc__.split('\n')[0]
    usage = __doc__
    min_args = 0
    max_args = 2

    def command(self):

        if not self.args or self.args[0] in ['--help', '-h', 'help']:
            print Archiver.__doc__
            return

        cmd = self.args[0]
        self._load_config()

        if cmd == 'update_first_publisher_date':
            pub_date.run()
        elif cmd == 'update_redirects':
             """
             Extract all change in publisher ids i.e.old and new publisher mapping.
             """
             _current_dir = os.path.dirname(os.path.realpath(__file__))
             _file_name = "redirects.json"
             _redirect_dir = "redirects"
             _file_path = "{}/{}/{}".format(_current_dir, _redirect_dir, _file_name)
             _db_conn = create_engine(config.get('sqlalchemy.url')).connect()
             _query = ''' 
			SELECT DISTINCT public.group.id, public.group.name AS current_name, revision.name AS old_name 
			FROM 
			public.group, (
					SELECT id, name, revision_timestamp, row_number() 
					OVER(PARTITION BY id ORDER BY revision_timestamp DESC) 
					FROM group_revision
			) AS revision 
			WHERE
			public.group.id=revision.id AND 
			public.group.name != revision.name 
			ORDER BY 
			public.group.name;
		      '''
             print(_query)
             res = _db_conn.execute(_query)
             if res:
                 _mapping = dict()
                 for _row in res:
                     _new_id = _row[1] # Current publisher id
                     _old_id = _row[2] # Old puiblisher id
                     if _new_id in _mapping:
                         _mapping[_new_id].append(_old_id)
                     else:
                         _mapping[_new_id] = [_old_id]
                 with open(_file_path, 'wb') as f:
                     json.dump(_mapping, f, ensure_ascii=False)
                     f.close()
                 print("New Mapping doc: {}".format(_file_path))
	     else:
                 print("Query resulted in zero rows")
             # Write the mapping to redirects folder json file
        else:
            log.error('Command {0} not recognized'.format(cmd))
