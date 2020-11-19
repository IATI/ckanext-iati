from ckan.lib.base import render, abort
from ckan.common import c, request, _
import ckan.lib.helpers as h
import ckan.logic as logic
import ckan.model as model
import ckan.plugins as p
from ckanext.iati.logic import action as iati_action
from ckan.controllers.organization import OrganizationController
from webhelpers.html import HTML, literal, tags, tools
from ckanext.iati.controllers.publisher_list_download import PublishersListDownload

import logging
log = logging.getLogger(__file__)

NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized
ValidationError = logic.ValidationError


class PublisherController(OrganizationController):

    def _guess_group_type(self, expecting_name=False):
        return 'organization'

    def members_read(self, id):
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}
        extra_vars = {}
        try:
            c.members = logic.get_action('member_list')(
                context, {'id': id, 'object_type': 'user'}
            )
            c.group_dict = logic.get_action('organization_show')(context, {'id': id})
            extra_vars.update({'group_type': c.group_dict.get('type', '')})
        except logic.NotAuthorized:
            p.toolkit.abort(401, p.toolkit._('Unauthorized to read group members %s') % '')
        except logic.NotFound:
            p.toolkit.abort(404, p.toolkit._('Group not found'))
        return render('organization/members_read.html', extra_vars=extra_vars)

    def dashboard_pending_organizations(self):
        log.debug('dashboard pending orgainzations')
        # Anonymous user should not be allowed to visit the link
        try:
            if not c.user:
                raise logic.NotAuthorized
            return render('user/dashboard_pending_organizations.html')
        except logic.NotAuthorized:
            p.toolkit.abort(401, p.toolkit._('Unauthorized to visit pending publisher page %s') % '')

    def dashboard_my_organizations(self):
        log.debug('dashboard my orgainzations')
        try:
            if not c.user:
                raise logic.NotAuthorized
            return render('user/my_organizations.html')
        except logic.NotAuthorized:
            p.toolkit.abort(401, p.toolkit._('Unauthorized to visit my publisher page  %s') % '')

    def index(self):
        return OrganizationController.index(self)

    def archiver_page(self, id):
        group_type = self._ensure_controller_matches_group_type(id)
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}
        c.group_dict = logic.get_action('organization_show')(context, {'id': id})
        group_type = c.group_dict['type']
        self._setup_template_variables(context, {'id': id, 'organization':c.group_dict},
                                       group_type=group_type)
        return render('organization/archiver.html',
                      extra_vars={'group_type': group_type})

    def dataset_archiver_page(self, id):
        vars = {}
        vars['id'] = id
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}
        pkg = logic.get_action('package_show')(context, {'id': id})
        vars['organization'] = pkg['organization']
        vars['package_id'] = True
        vars['pkg'] = pkg
        return render('user/archiver.html', extra_vars=vars)
