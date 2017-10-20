from setuptools import setup, find_packages
import sys, os

version = '0.3.1'

setup(name='ckanext-iati',
      version=version,
      description="CKAN Extension Code for the IATI Registry",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='iati un aid openaid',
      author='Open Knowledge Foundation',
      author_email='info@okfn.org',
      url='http://www.okfn.org',
      license='',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      namespace_packages=['ckanext'],
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-

      [ckan.plugins]
      iati_publishers = ckanext.iati.plugins:IatiPublishers
      iati_datasets = ckanext.iati.plugins:IatiDatasets
      iati_theme = ckanext.iati.plugins:IatiTheme
      iati_csv = ckanext.iati.plugins:IatiCsvImporter

      [paste.paster_command]
      iati-archiver=ckanext.iati.commands:Archiver
      iati-purge=ckanext.iati.commands:PurgeCmd
      iati-celery=ckanext.iati.command_celery:CeleryCmd

      [ckan.celery_task]
      tasks = ckanext.iati.celery_import:task_imports
      """,
      )
