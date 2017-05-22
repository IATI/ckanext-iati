import logging
import json
import csv
import tempfile
import datetime
from urlparse import urljoin

from pylons import config
import sqlalchemy

from ckan import logic

import ckan.plugins as p
import ckan.lib.helpers as h
import ckan.lib.dictization.model_dictize as model_dictize

import ckan.logic.action.get as get_core
import ckan.logic.action.create as create_core
import ckan.logic.action.update as update_core
import ckan.logic.action.patch as patch_core

import ckanext.iati.emailer as emailer

from paste.deploy.converters import asbool


log = logging.getLogger(__name__)

site_url = config.get('ckan.site_url', 'http://iatiregistry.org')

def package_create(context, data_dict):

    # The only thing we do here is remove some extras that are always
    # inherited from the dataset publisher, to avoid duplicating them
    _remove_extras_from_data_dict(data_dict)

    return create_core.package_create(context, data_dict)


def package_update(context, data_dict):

    # The only thing we do here is remove some extras that are always
    # inherited from the dataset publisher, to avoid duplicating them
    _remove_extras_from_data_dict(data_dict)

    # if dataset has more then one resource get the one that has
    # closest date to date today and remove the others
    resources = data_dict['resources']

    date_today = datetime.datetime.now()
    resource_to_update = []


    resources_created = [x['created'] for x in resources]
    near = min(resources_created,
            key=lambda d: abs(datetime.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S.%f") - date_today))

    for resource in resources:
        if resource['created'] == near:
            resource_to_update.append(resource)

    data_dict['resources'] = resource_to_update

    return update_core.package_update(context, data_dict)

def package_patch(context, data_dict):

    # The only thing we do here is remove some extras that are always
    # inherited from the dataset publisher, to avoid duplicating them
    _remove_extras_from_data_dict(data_dict)

    return patch_core.package_patch(context, data_dict)

def organization_create(context, data_dict):

    # When creating a publisher, if the user is not a sysadmin it will be
    # created as pending, and sysadmins notified

    notify_sysadmins = False
    try:
        p.toolkit.check_access('sysadmin', context, data_dict)
    except p.toolkit.NotAuthorized:
        # Not a sysadmin, create as pending and notify sysadmins (if all went
        # well)
        context['__iati_state_pending'] = True
        data_dict['state'] = 'approval_needed'
        notify_sysadmins = True
    org_dict = create_core.organization_create(context, data_dict)

    if notify_sysadmins:
        _send_new_publisher_email(context, org_dict)

    return org_dict


def organization_update(context, data_dict):

    # Check if state is set from pending to active so we can notify users

    old_org_dict = p.toolkit.get_action('organization_show')({},
            {'id': data_dict.get('id') or data_dict.get('name')})
    old_state = old_org_dict.get('state')

    new_org_dict = update_core.organization_update(context, data_dict)
    new_state = new_org_dict.get('state')

    if old_state == 'approval_needed' and new_state == 'active':
        # Notify users
        _send_activation_notification_email(context, new_org_dict)
        h.flash_success('Publisher activated, a notification email has been sent to its administrators.')

    return new_org_dict

@p.toolkit.side_effect_free
def group_list(context, data_dict):
    '''
        Warning: This API request is deprecated. Please use the equivalent one
        on version 3 of the API:
        http://iatiregistry.org/api/action/organization_list
    '''
    p.toolkit.check_access('group_list', context, data_dict)
    data_dict['groups'] = data_dict.pop('organizations', [])
    data_dict['type'] = 'organization'
    return get_core._group_or_org_list(context, data_dict, is_org=True)

@p.toolkit.side_effect_free
def group_show(context, data_dict):
    '''
        Warning: This API request is deprecated. Please use the equivalent one
        on version 3 of the API:
        http://iatiregistry.org/api/action/organization_show
    '''
    return get_core.organization_show(context, data_dict)

def _remove_extras_from_data_dict(data_dict):
    # Remove these extras, as they are always inherited from the publishers
    # and we don't want to store them
    extras_to_remove = ('publisher_source_type',
                        'publisher_organization_type',
                        'publisher_country',
                        'publisher_iati_id',
                       )
    data_dict['extras'] = [e for e in data_dict.get('extras', []) if e.get('key') and e['key'] not in extras_to_remove]


@p.toolkit.side_effect_free
def package_show_rest(context, data_dict):

    #  Add some extras to the dataset from its publisher.

    #  The ideal place to do this should be the after_show hook on the
    #  iati_datasets plugin but package_show_rest does not call it in core.

    package_dict = get_core.package_show_rest(context, data_dict)

    group = context['package'].groups[0] if len(context['package'].groups) else None
    if group:
        new_extras = []
        for key in ('publisher_source_type', 'publisher_organization_type', 'publisher_country',
                    'publisher_iati_id',):
            new_extras.append({'key': key, 'value': group.get(key, '')})

        package_dict['extras'].update(new_extras)

    return package_dict


def issues_report_csv(context, data_dict):

    logic.check_access('issues_report_csv', context, data_dict)

    publisher_name = data_dict.get('publisher', None)

    issues = {}

    # Get packages with issues
    if publisher_name:
        result = packages_with_issues_for_a_publisher(context, publisher_name)
        if result['count'] > 0:
            issues[publisher_name] = result['results']

    else:
        # Get all the publishers whose datasets have issues
        data_dict = {
            'q': 'issue_type:[\'\' TO *]',
            'facet.field': ['organization'],
            'rows': 0,
        }
        result = logic.get_action('package_search')(context, data_dict)
        if result['count'] > 0:
            publishers = result['facets']['organization']
            for publisher_name, count in publishers.iteritems():
                result = packages_with_issues_for_a_publisher(context, publisher_name)
                issues[publisher_name] = result['results']


    fd, tmp_file_path = tempfile.mkstemp(suffix='.csv')

    def get_extra(pkg_dict, key, default=None):
        for extra in pkg_dict['extras']:
            if extra['key'] == key:
                if extra['value'][:1] == '"':
                    extra['value'] = json.loads(extra['value'])
                return extra['value']

        return default

    with open(tmp_file_path, 'w') as f:
        field_names = ['publisher', 'dataset', 'url', 'file_url', 'issue_type', 'issue_date', 'issue_message']
        writer = csv.DictWriter(f, fieldnames=field_names, quoting=csv.QUOTE_ALL)
        writer.writerow(dict( (n,n) for n in field_names ))
        for publisher, datasets in issues.iteritems():
            for dataset in datasets:
                url = urljoin(site_url, '/dataset/' + dataset['name'])
                if len(dataset['resources']):
                    file_url = dataset['resources'][0]['url']
                else:
                    file_url = ''

                writer.writerow({
                    'publisher': publisher,
                    'dataset': dataset['name'],
                    'url': url,
                    'file_url': file_url,
                    'issue_type': get_extra(dataset, 'issue_type', ''),
                    'issue_date': get_extra(dataset, 'issue_date', ''),
                    'issue_message': get_extra(dataset, 'issue_message', ''),
                })

        return {
            'file': tmp_file_path,
        }


def packages_with_issues_for_a_publisher(context, publisher_name):
        data_dict = {
            'q': 'issue_type:[\'\' TO *]',
            'fq': 'organization:{0}'.format(publisher_name),
            'rows': 1000,
        }

        return logic.get_action('package_search')(context, data_dict)

def _get_sysadmins(context):

    model = context['model']

    q = model.Session.query(model.User) \
             .filter(model.User.sysadmin==True)
    return q.all()

def _send_new_publisher_email(context, organization_dict):

    publisher_link = urljoin(site_url, '/publisher/' + organization_dict['name'])

    for sysadmin in _get_sysadmins(context):
        if sysadmin.email:
            body = emailer.new_publisher_body_template.format(
               sysadmin_name=sysadmin.name,
               user_name=context['user'],
               site_url=site_url,
               publisher_title=organization_dict['title'].encode('utf8'),
               publisher_link=publisher_link,
            )
            subject = "[IATI Registry] New Publisher: {0}".format(organization_dict['title'].encode('utf8'))
            emailer.send_email(body, subject, sysadmin.email)
            log.debug('[email] New publisher notification email sent to sysadmin {0}'.format(sysadmin.name))


def _send_activation_notification_email(context, organization_dict):

    model = context['model']

    members = p.toolkit.get_action('member_list')(context, {'id': organization_dict['id']})
    admins = [m for m in members if m[1] == 'user' and m[2] == 'Admin']

    subject = config.get('iati.publisher_activation_email_subject', 'IATI Registry Publisher Activation')

    group_link = urljoin(site_url, '/publisher/' + organization_dict['name'])

    for admin in admins:
        user = model.User.get(admin[0])
        if user and user.email:
            user_name = user.fullname or user.name
            content = emailer.publisher_activation_body_template.format(user_name=user_name.encode('utf8'),
                    group_title=organization_dict['title'].encode('utf8'), group_link=group_link, user_email=user.email,
                    site_url=site_url)
            emailer.send_email(content, subject, user.email)
            log.debug('[email] Publisher activated notification email sent to user {0}'.format(user.name))

def _unpick_search(sort, allowed_fields=None, total=None):
    ''' This is a helper function that takes a sort string
    eg 'name asc, last_modified desc' and returns a list of
    split field order eg [('name', 'asc'), ('last_modified', 'desc')]
    allowed_fields can limit which field names are ok.
    total controls how many sorts can be specifed '''
    sorts = []
    split_sort = sort.split(',')
    for part in split_sort:
        split_part = part.strip().split()
        field = split_part[0]
        if len(split_part) > 1:
            order = split_part[1].lower()
        else:
            order = 'asc'
        if allowed_fields:
            if field not in allowed_fields:
                raise ValidationError('Cannot sort by field `%s`' % field)
        if order not in ['asc', 'desc']:
            raise ValidationError('Invalid sort direction `%s`' % order)
        sorts.append((field, order))
    if total and len(sorts) > total:
        raise ValidationError(
            'Too many sort criteria provided only %s allowed' % total)
    return sorts

def _group_or_org_list_optimized(context, data_dict, is_org=False):
    model = context['model']
    api = context.get('api_version')
    groups = data_dict.get('groups')
    group_type = data_dict.get('type', 'group')
    ref_group_by = 'id' if api == 2 else 'name'

    sort = data_dict.get('sort', 'name')
    q = data_dict.get('q')

    # order_by deprecated in ckan 1.8
    # if it is supplied and sort isn't use order_by and raise a warning
    order_by = data_dict.get('order_by', '')
    if order_by:
        log.warn('`order_by` deprecated please use `sort`')
        if not data_dict.get('sort'):
            sort = order_by
    # if the sort is packages and no sort direction is supplied we want to do a
    # reverse sort to maintain compatibility.
    if sort.strip() in ('packages', 'package_count'):
        sort = 'package_count desc'

    sort_info = _unpick_search(sort,
                               allowed_fields=['name', 'packages',
                                               'package_count', 'title'],
                               total=1)

    all_fields = data_dict.get('all_fields', None)
    include_extras = all_fields and \
                     asbool(data_dict.get('include_extras', False))

    query = model.Session.query(model.Group)
    if include_extras:
        # this does an eager load of the extras, avoiding an sql query every
        # time group_list_dictize accesses a group's extra.
        query = query.options(sqlalchemy.orm.joinedload(model.Group._extras))
    query = query.filter(model.Group.state == 'active')
    if groups:
        query = query.filter(model.Group.name.in_(groups))
    if q:
        q = u'%{0}%'.format(q)
        query = query.filter(_or_(
            model.Group.name.ilike(q),
            model.Group.title.ilike(q),
            model.Group.description.ilike(q),
        ))

    query = query.filter(model.Group.is_organization == is_org)
    if not is_org:
        query = query.filter(model.Group.type == group_type)

    groups = query.all()
    if all_fields:
        include_tags = asbool(data_dict.get('include_tags', False))
    else:
        include_tags = False
    # even if we are not going to return all_fields, we need to dictize all the
    # groups so that we can sort by any field.
    group_list = model_dictize.group_list_dictize(
        groups, context,
        sort_key=lambda x: x[sort_info[0][0]],
        reverse=sort_info[0][1] == 'desc',
        with_package_counts=all_fields or
        sort_info[0][0] in ('packages', 'package_count'),
        include_groups=asbool(data_dict.get('include_groups', False)),
        include_tags=include_tags,
        include_extras=include_extras,
        )

    if not all_fields:
        group_list = [group[ref_group_by] for group in group_list]

    return group_list


def organization_list_publisher_page(context, data_dict):
    #_check_access('organization_list_publisher_page', context, data_dict)
    data_dict['groups'] = data_dict.pop('organizations', [])
    data_dict['type'] = 'organization'
    return _group_or_org_list_optimized(context, data_dict, is_org=True)
