import sys
import logging
from ckan.lib.cli import CkanCommand

from ckanext.iati.custom_archiver import run as run_archiver

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
