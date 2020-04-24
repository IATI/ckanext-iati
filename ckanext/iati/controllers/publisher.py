from ckan.lib.base import render, BaseController
from ckan.common import c, request
import ckan.lib.helpers as h
import ckan.logic as logic
import ckan.model as model
import ckan.plugins as p
from ckanext.iati.logic import action as iati_action
from ckan.controllers.organization import OrganizationController
from webhelpers.html import HTML, literal, tags, tools

import logging
log = logging.getLogger(__file__)

NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized
ValidationError = logic.ValidationError


class PublisherController(OrganizationController):

    def _guess_group_type(self, expecting_name=False):
        return 'organization'

    def publisher_index(self):
        """
        Modified version of organization index.
        - Only fo type organization.
        - Included pagination
        - Wide range of search functionality i.e. search by name, title, publisher_iati_id, licence_id
        - Searchable by all the organization extra fields.
        """
        group_type = self._guess_group_type()

        page = h.get_page_number(request.params) or 1
        items_per_page = 21

        context = {'model': model, 'session': model.Session,
                   'user': c.user, 'for_view': True,
                   'with_private': False}

        q = c.q = request.params.get('q', '')
        sort_by = c.sort_by_selected = request.params.get('sort')
        try:
            self._check_access('site_read', context)
            self._check_access('group_list', context)
        except NotAuthorized:
            abort(403, _('Not authorized to see this page'))

        # pass user info to context as needed to view private datasets of
        # orgs correctly
        if c.userobj:
            context['user_id'] = c.userobj.id
            context['user_is_admin'] = c.userobj.sysadmin

        try:
            data_dict_global_results = {
                'all_fields': False,
                'q': q,
                'sort': sort_by,
                'type': group_type or 'group',
            }
            global_results = self._action('group_list')(
                context, data_dict_global_results)
        except ValidationError as e:
            if e.error_dict and e.error_dict.get('message'):
                msg = e.error_dict['message']
            else:
                msg = str(e)
            h.flash_error(msg)
            c.page = h.Page([], 0)
            return render(self._index_template(group_type),
                          extra_vars={'group_type': group_type})

        data_dict_page_results = {
            'all_fields': True,
            'q': q,
            'sort': sort_by,
            'type': group_type or 'group',
            'limit': items_per_page,
            'offset': items_per_page * (page - 1),
            'include_extras': True
        }
        page_results = iati_action.custom_group_list(context, data_dict_page_results)

        c.page = h.Page(
            collection=global_results,
            page=page,
            url=h.pager_url,
            items_per_page=items_per_page,
        )

        c.page.items = page_results
        return render(self._index_template(group_type),
                      extra_vars={'group_type': group_type})

    def members_read(self, id):
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}

        try:
            c.members = logic.get_action('member_list')(
                context, {'id': id, 'object_type': 'user'}
            )
            c.group_dict = logic.get_action('organization_show')(context, {'id': id})
            extra_vars = {}
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

