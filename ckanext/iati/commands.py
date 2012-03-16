import os
import sys
from ckan.lib.cli import CkanCommand

from ckanext.iati.archiver import run as run_archiver

class Archiver(CkanCommand):
    '''
    Download and save copies of all IATI activity files, extract some metrics
    from them and store them as extras.

    Usage:

        paster iati-archiver update [{package-id}]
           - Archive all activity files or just those belonging to a specific package
             if a package id is provided

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    min_args = 0
    max_args = 2
    pkg_names = []

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
            package = unicode(self.args[1]) if len(self.args) > 1 else None

            result = run_archiver(package)
            if not result:
                sys.exit(1)
        else:
            log.error('Command %s not recognized' % (cmd,))


