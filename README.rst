International Aid Transparency Initiative (IATI) Registry Extension for CKAN
============================================================================


* `Installation`_
* `Migrating from the old Registry version`_
* `Configuration`_
* `General workflow`_
* `Main customizations`_
* `Copying and License`_

Installation
------------

The current version of ckanext-iati has been developed and tested again
**CKAN 2.1.x**. We assume a running CKAN 2.1.x instance.

The installation has the following steps, assuming you have a running
copy of CKAN:

#. Install the extension from its source repository::

    (pyenv) $ pip install -e git+https://github.com/okfn/ckanext-iati#egg=ckanext-iati

#. Install dependencies::

    (pyenv) $ pip install -r ckanext-iati/pip-requirements.txt

Set up the configuration options as described in the `Configuration`_ section.


Migrating from the old Registry version
---------------------------------------

The previous version of the registry run on CKAN 1.5.1. To upgrade the database
follow the following steps:

#. Backup the CKAN 1.5.1 database

#. Run the normal update command::

    (pyenv) $ cd ckan
    (pyenv) $ paster db upgrade

#. Run the SQL script to transform Groups to Organizations::

    sudo -u postgres psql -f ckanext-iati/scripts/groups_to_orgs.sql

#. Edit the ``users_to_members.py`` script with a suitable API key and run it
   to create members for the migrated organizations::

    (pyenv) $ python ckanext-iati/scripts/users_to_members.py

#. Run a final SQL script to cleanup the database (may take a long time)::

    sudo -u postgres psql -f ckanext-iati/scripts/cleanup_db.sql


Configuration
-------------

Create a sysadmin user called ``iati-archiver`` and note down its API key,
you will need to add it to the ini file::


(pyenv) $ cd ckan
(pyenv) $ paster sysadmin add iati-archiver

These are the configuration options used by the extension (generic options
like ``ckan.site_id``, ``solr_url``, etc are not included)::


    # Load only these four plugins
    ckan.plugins = iati_publishers iati_datasets iati_theme iati_csv

    # Needed for the search facets to be displayed properly until #599 is
    # fixed on CKAN core
    search.facets.default=1000

    # File preview service URL and CSV export service URL.
    # If these are commented out, the links won't appear in the frontend
    iati.preview_service = http://tools.aidinfolabs.org/showmydata/index.php?url=%s
    iati.csv_service = http://tools.aidinfolabs.org/csv/direct_from_registry/?xml=%s

    # User name and API key for the iati-archiver sysadmin user
    iati.admin_user.name=iati-archiver
    iati.admin_user.api_key={api-key}

    # Google Analytics id to be used when inserting the code
    # If this option is commented out, the code won't be added to the frontend
    iati.google_analytics.id=UA-XXXXXXX-XX

    # Email settings
    # Make sure smtp_server is properly setted (normally to localhost) the rest
    # of the defaults should be good enough:

    # Address from where the email notifactions are sent, default is 'no-reply@iatiregistry.org'
    #iati.email=

    # Subject of the email sent to publishers when activated, default is 'IATI Registry Publisher Activation'
    #iati.publisher_activation_email_subject=

    # Allowed values for the IATI Standard Version (iati_version) field, default is '1.01 1.02 1.03 1.04 2.01'
    #iati.standard_versions



To ensure that the logging for the archiver works fine and prevent permissions
problems, use the following logging configuration::

    ## Logging configuration
    [loggers]
    keys = root, ckan, ckanext, iati_archiver

    [handlers]
    keys = console

    [formatters]
    keys = generic

    [logger_root]
    level = WARNING
    handlers = console

    [logger_ckan]
    level = INFO
    handlers = console
    qualname = ckan
    propagate = 0

    [logger_ckanext]
    level = INFO
    handlers = console
    qualname = ckanext
    propagate = 0

    [logger_iati_archiver]
    level = DEBUG
    handlers = console
    qualname = iati_archiver
    propagate = 0

    [handler_console]
    class = StreamHandler
    args = (sys.stderr,)
    level = NOTSET
    formatter = generic

    [formatter_generic]
    format = %(asctime)s %(levelname)-5.5s [%(name)s] %(message)s

To set up the `Daily archiver and issue checker`_, you need to create a cron
job that calls the command once a day. See the dedicated section for details.


General workflow
----------------

The registry holds *Datasets* for aid spending data following the
`IATI Standard`_. Each CKAN dataset has a single resource, an IATI XML file,
which can be of type 'activity' or 'organisation'.

Datasets are created by *Publishers*, implemented with Organizations in CKAN.

Everyone can register as a *User* on the registry, and create a Publisher. When
a publisher is created, it is set with a state of 'pending', and an email is
sent to site administrators (all sysadmins).

Sysadmins can change the state of the Publishers to 'active' to approve it or
'deleted' to disapprove it. Once the Publisher is activated, the user that
created it gets an email notification and from that moment they can create
datasets.

Datasets can be created or updated via:

1. The web form
2. The `CSV Importer / Exporter`_
3. Third party apps that use the API (eg `AidStream`_)

.. _`IATI Standard`: http://iatistandard.org
.. _`AidStream`: http://aidstream.org


Main customizations
-------------------

All different plugins are located in ``ckanext/iati/plugins.py``.


Theme
+++++

Custom theme based on a design provided by the client. The main changes are the
organization listing page, the search facets as dropdown in the main search
page, the dataset page and the datasets listings.

Custom Organizations schema
+++++++++++++++++++++++++++

A number of fields are added to the default group schema in CKAN to store extra
metadata about the publishers, using ``IGroupForm`` (see the ``IatiPublishers``
plugin).

Note that this is not as polished as ``IDatasetForm``, so we still need for
instance to manually set up the ``/publisher`` routes to point to the group
controller. This causes problems sometimes, as the redirects lose the query
parameters (or also see eg the ``publishers_pagination`` helper function).


Custom Dataset schema
+++++++++++++++++++++

Datasets have also custom fields which are stored as extras (see the
``IatiDatasets`` plugin). Datasets also inherit fields from the Publisher they
belong to (the ones starting with ``publisher_``. This is done on the
``after_show`` hook.

The ``before_index`` hook is also used to index the human readable form for the
facets.

There is a slightly modified auth function for ``package_create`` that checks
that the org they user belongs to is active.


Email notifications
+++++++++++++++++++

Emails notifications are sent:

* To sysadmins when a new publisher is registered, so they can approve it or
  not.

* To users when their publisher has been activated.

The code to actual send the emails is in ``ckanext/iati/emailer.py``

CSV Importer / Exporter
+++++++++++++++++++++++

Users can download all metadata for the datasets they have permissions on (ie
the ones of their publisher) in a CSV file.

Once updated, the file can be reuploaded and new datasets will be created or
existing ones updated.

The code that handles this is in
``ckanext-iati/ckanext/iati/controllers/spreadsheet.py``

Daily archiver and issue checker
++++++++++++++++++++++++++++++++

A script runs every night in order to download all files, check if they have
changed and extract some metadata from the actual contents. It also checks for
issues like missing files, wrong formats, etc.

If the contents of the file have changed, the new fields are stored as extras
(right now these are number of activities ``activity_count`` and last modified
date for the data ``data_updated``). The file size is also updated.

Issues are stored as extras as well with three different fields:
``issue_type``, ``issue_description`` and ``issue_date``. These are later used
to display the issue on the frontend, as well as a filter to find out which
datasets have issues on the search page.

There is also an Issue Report for sysadmins that downloads a CSV listing all
issues for all datasets (accessible at ``/report/issues``).

To run the archiver manually for all datasets, run the following command (it
will take a long time)::

    cd ckanext-iati
    (pyenv) $ paster iati-archiver update -c ../ckan/development.ini

To run it just on a particular dataset::

    (pyenv) $ paster iati-archiver update {dataset-name} -c ../ckan/development.ini

To run it on all datasets for a particular publisher::

    (pyenv) $ paster iati-archiver update -p {publisher-name} -c ../ckan/development.ini

On a production or staging server you would want to set it up as cron job that
runs the command once a day (eg 5 minutes after midnight ). Add the following
to the relevant user crontab (generally ``okfn``)::

    05 00  *   *   *  /usr/lib/ckan/iati/bin/paster --plugin=ckanext-iati iati-archiver update -c /etc/ckan/iati/production.ini >> /tmp/iati_archiver_2_out.log 2>&1


Copying and License
-------------------

This material is copyright (c) 2010-2013 Open Knowledge Foundation.

It is open and licensed under the GNU Affero General Public License (AGPL) v3.0
whose full text may be found at:

http://www.fsf.org/licensing/licenses/agpl-3.0.html

This extension uses the `TableSorter`_ jQuery plugin by Christian Bach,
released under the `MIT license`_.

.. _TableSorter: http://tablesorter.com
.. _`MIT license`: http://www.opensource.org/licenses/mit-license.php
