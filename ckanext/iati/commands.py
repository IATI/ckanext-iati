import sys
import logging
# from ckan.lib.cli import CkanCommand
from ckanext.iati.archiver import run as run_archiver
from ckan.common import config
from ckanext.iati import model as iati_model
import json
import os
import click

log = logging.getLogger('iati_archiver')


@click.group(help='''
    Usage:
        ckan iati-archiver update [-p {publisher-id}] [{package-id}]
           - Archive all activity files or just those belonging to a specific
             package or publisher.
    ''')
def iati_archiver():
    '''
    Download and save copies of all IATI activity files, extract some metrics
    from them and store them as extras.
    '''


@iati_archiver.command(help='''
    Usage:
        ckan iati-archiver update [-p {publisher-id}] [{package-id}]
           - Archive all activity files or just those belonging to a specific
             package or publisher.
    ''')
@click.option('-p', '--publisher-id', type=str, help='Archive datasets only from this publisher')
@click.argument('package_id', default=None, type=str, required=False)
def update(publisher_id=None, package_id=None):
    run_archiver(package_id, publisher_id)

@click.command()
def iati_purge(help='Purges deleted datasets.'):
    import ckan.model as model
    deleted_packages = list(model.Session.query(
                model.Package).filter_by(state=model.State.DELETED))
    pkg_len = len(deleted_packages)

    for i, pkg in enumerate(deleted_packages, start=1):
        log.info('Purging {0}/{1}: {2}'.format(i, pkg_len, pkg.id))
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

    log.info('Purge complete')

@click.group(help='Ti initalise the db and also to fetch redirects from the database.')
def iati_redirects():
    """
    Ti initalise the db and also to fetch redirects from the database.
    """
    pass


@iati_redirects.command(help='Initializes the database tables.')
def initdb():
    iati_model.init_tables()


@iati_redirects.command(help='Extract all change in publisher ids i.e.old and new publisher mapping.')
def update_redirects():
    iati_model.IATIRedirects.update_redirects()


cmds = [
    iati_archiver,
    iati_redirects,
    iati_purge
]
