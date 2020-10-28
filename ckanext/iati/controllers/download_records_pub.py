from ckanext.iati.controllers.spreadsheet import CSVController
from ckan.common import c, request
import ckan.lib.helpers as h
import ckan.logic as logic
import ckan.model as model
import ckan.plugins as p
from ckanext.iati.logic import internal_action as iati_action
import logging

log = logging.getLogger(__name__)
NotFound = logic.NotFound
NotAuthorized = logic.NotAuthorized
_check_access = logic.check_access
ValidationError = logic.ValidationError


class PublisherDownloadRecords(CSVController):
    """
    Inherit from CSV controller.
    Modify publisher page search functionality to render different template.
    Download the of records
    """
    def _guess_group_type(self, expecting_name=False):
        return 'organization'

    def publisher_download_index(self):
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
        sort_by = c.sort_by_selected = request.params.get('sort', 'name')
        try:
            _check_access('site_read', context)
            _check_access('group_list', context)
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
            global_results = p.toolkit.get_action('group_list')(
                context, data_dict_global_results)
        except ValidationError as e:
            if e.error_dict and e.error_dict.get('message'):
                msg = e.error_dict['message']
            else:
                msg = str(e)
            h.flash_error(msg)
            c.page = h.Page([], 0)
            return p.toolkit.render('csv/index.html', extra_vars={'c': c})

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
        return p.toolkit.render('csv/index.html', extra_vars={'c': c})

    def download(self, publisher):

        context = {'model': model, 'user': c.user or c.author}

        if publisher not in ('all', 'template'):
            try:
                org = p.toolkit.get_action('organization_show')(context, {'id': publisher})
                output = self.write_csv_file(publisher)
            except p.toolkit.ObjectNotFound:
                p.toolkit.abort(404, 'Publisher not found')
        else:
            output = self.write_csv_file(publisher)

        file_name = publisher if publisher else 'iati-registry-records'
        p.toolkit.response.headers['Content-type'] = 'text/csv'
        p.toolkit.response.headers['Content-disposition'] = 'attachment;filename=%s.csv' % str(file_name)

        return output
