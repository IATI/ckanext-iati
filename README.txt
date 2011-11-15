
International Aid Transparency Initiative Registry Extensions to CKAN

* Publisher Model
* Institutional Authorization
* Previews
* Solr facets by institution type, recipient country and file type
* Custom forms and theme


Installation and Configuration
==============================

Since the IATI extension does influcence CKAN in a number of sensitive
points, it should only be used against tested versions. The latest 
release known to be compatible is: 

  1.3.3b, Debian-packaged

The installation has the following steps, assuming you have a running 
copy of CKAN:

1) Install the extension from its source repository (a Debian package 
is not available at this time):

(env)$ pip install -e git+https://github.com/okfn/ckanext-iati#egg=ckanext-iati

You probably also want to install the ckanext-wordpresser and
ckanext-archiver packages.  See their respective documentation for
install notes.

2) Copy or symlink the modified Solr schema.xml into the Solr core 
´´conf/´´ directory, remove any existing index and restart Solr. 

NB: IATI uses a customized search index schema to accomodate the 
groups_types field not present in generic CKAN.

3) Add the following configuration options to your .ini file:

# Approval message sender email: 
iati.email = activation@iatiregistry.org 

# File preview service URL (notice the token that will be replaced with the file URL):
iati.preview_service = http://dev.yipl.com.np/iati/tools/public/api/activityviewer?xmlUrl=%s

ckan.site_title = IATI Registry

# Used in approval mails, make sure its correct:
ckan.site_url = http://iati.test.ckan.net

# Add any other plugins you want to use:
ckan.plugins = iati_forms iati_approval iati_group_authz iati_package_authz iati_license_override wordpresser synchronous_search

# Use a proxy wordpress to provide help & about pages (etc)
wordpresser.proxy_host = http://iatiregistry.wordpress.org/

# Use solr and facet over specific fields:
search_backend = solr
search.facets = groups groups_types extras_country extras_file_type

(Don't forget to also add a 'solr_url').

# User credentials used in the archiver
iati.admin_user.name = <user_name>
iati.admin_user.api_key = <api_key>
 

Overall workflow for IATI
=========================

Publishers
----------

(1) All packages are released by IATI publishers, normal users cannot submit 
packages. Publishers (CKAN Entity: Group, renamed in a custom i18n) themselves 
are typed as one of "Primary Source" or "Secondary Source". The type is stored 
as a "type" extra on the group and then folded into each indexed package via 
a monkey-patched as_dict() method on Package. This allows us to facet over 
packages associated with a specific type of Publisher.

(2) Anyone can sign up to the site (previously only via OpenID, we should 
promote the fact that CKAN now has normal user accounts) and create Publisher. 
The publisher is then created in a "pending" state (monkey-patched VDM) and an 
email is dispatched to all users that are sysadmins on the site 
(ckanext.iati.approval) to review the application. Meanwhile, the pending 
publisher is not shown in any group listings and when called directly, a warning 
box is included on the page to make the pending status clear. Admins can log 
in and edit the publisher to select the "active" or "deleted" state depending 
on whether a publisher is valid or not. 

(3) When creating a publisher both a "Group" and "AuthorizationGroup" are 
created. The AuthorizationGroup is named after the (Package) Group, in the 
form group-%(group.id)s-authz. It is updated whenever the Group/Publisher is 
edited and member lists are kept in sync: Group members are added as AuthzGroup 
admins and the AuthzGroup has at least read rights on the actual Group 
(ckanext.iati.authz).


Packages
--------

(4) Packages can only be created by those that are both registered as users 
and a member of at least one active publisher. This is checked via a helpers.py 
monkey patch "am_authorized_with_publisher" (ckanext.iati.patch). 

(5) When a package is created, a post-creation hook is used to replace its 
default authorization mode is changed: the individual user is removed as a 
package admin and replaced by the first authz group that he is a member of. 
This way, all members of the associated publisher are automatically admins of 
the new package and removing the individual user would not orphan the package. 


Metadata schema and data previews
---------------------------------

(6) The custom form for IATI contains a series of specific fields, one of which 
is the country. A list of available countries is in ckanext.iati.controllers.country 
and it should be extended with geographic regions as this seems to be the only 
level of reporting some entities (e.g. Hewlett) do. 

(7) The IATI license has not yet been added to the license selection drop-down.

(8) Most of the more specific form fields could easily be derived from the IATI 
report data itself. 


Archiver command
================

The extension includes a paster command that will download all IATI XML files
(i.e. all resources), parse them and extract a couple of variables, which will
be stored in extras. To run it you must install ckanext-archiver. To run the
command, assuming you are on the ckanext-iati directory::

    paster iati-archiver update --config=../ckan/development.ini
