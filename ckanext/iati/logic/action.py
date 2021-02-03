import logging
import json
import csv
import tempfile
from urlparse import urljoin
import inspect
from pylons import config
import sqlalchemy
import sys
from ckan import logic

import ckan.authz as authz
import ckan.plugins as p
import ckan.lib.helpers as h
import ckan.lib.dictization.model_dictize as model_dictize
import ckan.model as model
import ckan.logic.action.get as get_core
import ckan.logic.action.create as create_core
import ckan.logic.action.update as update_core
import ckan.logic.action.patch as patch_core

import ckanext.iati.emailer as emailer
import ckanext.iati.helpers as hlp
from sqlalchemy import and_

from paste.deploy.converters import asbool
from ckan.common import _
import ckan
import cStringIO
import codecs

log = logging.getLogger(__name__)

site_url = config.get('ckan.site_url', 'http://iatiregistry.org')

_validate = ckan.lib.navl.dictization_functions.validate
_table_dictize = ckan.lib.dictization.table_dictize
NotFound = logic.NotFound
ValidationError = logic.ValidationError
_get_or_bust = logic.get_or_bust

_select = sqlalchemy.sql.select
_aliased = sqlalchemy.orm.aliased
_or_ = sqlalchemy.or_
_and_ = sqlalchemy.and_
_func = sqlalchemy.func
_desc = sqlalchemy.desc
_case = sqlalchemy.case
_text = sqlalchemy.text


def package_create(context, data_dict):

    # The only thing we do here is remove some extras that are always
    # inherited from the dataset publisher, to avoid duplicating them
    _remove_extras_from_data_dict(data_dict)
    created_package = create_core.package_create(context, data_dict)

    # Part of first publisher date patch - after package create patch the organization
    if 'owner_org' in data_dict.keys():
        hlp.first_published_date_patch(created_package.get('owner_org'))

    return created_package


def package_update(context, data_dict):
    
    # Part of first publisher date patch
    if 'owner_org' in data_dict.keys():
        hlp.first_published_date_patch(data_dict.get('owner_org'))
    # The only thing we do here is remove some extras that are always
    # inherited from the dataset publisher, to avoid duplicating them
    _remove_extras_from_data_dict(data_dict)

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

    # Patch for publisher first published date
    data_dict = hlp.publisher_first_published_date_validator(data_dict)

    new_org_dict = update_core.organization_update(context, data_dict)
    new_state = new_org_dict.get('state')

    if old_state == 'approval_needed' and new_state == 'active':
        # Notify users
        _send_activation_notification_email(context, new_org_dict)
        h.flash_success('Publisher activated, a notification email has been sent to its administrators.')

    return new_org_dict


def organization_patch(context, data_dict):

    if "publisher_first_publish_date" in data_dict:
        data_dict = hlp.publisher_first_published_date_validator(data_dict)

    return patch_core.organization_patch(context, data_dict)


@p.toolkit.side_effect_free
def group_list(context, data_dict):
    """
    Warning: This API request is deprecated. Please use the equivalent one
        on version 3 of the API:
        http://iatiregistry.org/api/action/organization_list
    :param context:
    :param data_dict:
    :return:
    """
    p.toolkit.check_access('group_list', context, data_dict)
    data_dict['groups'] = data_dict.pop('organizations', [])
    data_dict.setdefault('type', 'organization')
    return p.toolkit.get_action('organization_list')(context, data_dict)


@p.toolkit.side_effect_free
def group_show(context, data_dict):
    """
    Warning: This API request is deprecated. Please use the equivalent one
        on version 3 of the API:
        http://iatiregistry.org/api/action/organization_show
    :param context:
    :param data_dict:
    :return:
    """
    return p.toolkit.get_action('organization_show')(context, data_dict)


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


def issues_write_to_csv(field_names, issues):

    fd, tmp_file_path = tempfile.mkstemp(suffix='.csv')

    with open(tmp_file_path, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=field_names, quoting=csv.QUOTE_ALL)
        writer.writerow(dict((n, n) for n in field_names))
        for issue_row in issues:
            del issue_row['publisher_title']
            del issue_row['dataset_title']
            writer.writerow(issue_row)

    return {
        'file': tmp_file_path,
    }


def issues_report_csv(context, data_dict):

    is_download = data_dict.get('is_download', None)
    del data_dict['is_download']

    logic.check_access('issues_report_csv', context, data_dict)

    publisher_name = data_dict.get('publisher', None)

    issues = {}
    field_names = ['publisher', 'dataset', 'url', 'file_url', 'issue_type', 'issue_date', 'issue_message']
    issuues_report = []

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

    def get_extra(pkg_dict, key, default=None):
        for extra in pkg_dict['extras']:
            if extra['key'] == key:
                if extra['value'][:1] == '"':
                    extra['value'] = json.loads(extra['value'])
                return extra['value']

        return default

    for publisher, datasets in issues.iteritems():
        for dataset in datasets:
            url = urljoin(site_url, '/dataset/' + dataset['name'])
            if len(dataset['resources']):
                file_url = dataset['resources'][0]['url']
            else:
                file_url = ''

            issuues_report.append({
                                'publisher': publisher,
                                'dataset': dataset['name'],
                                'url': url,
                                'file_url': file_url,
                                'issue_type': get_extra(dataset, 'issue_type', ''),
                                'issue_date': get_extra(dataset, 'issue_date', ''),
                                'issue_message': get_extra(dataset, 'issue_message', ''),
                                'publisher_title': dataset['organization']['title'],
                                'dataset_title': format(dataset['title'])})
    if is_download:
        return issues_write_to_csv(field_names, issuues_report)
    else:
        return issuues_report


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
             .filter(_and_(model.User.sysadmin==True, model.User.state=='active'))
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


def _custom_group_or_org_list(context, data_dict, is_org=True, bypass_limit_internal=False):
    """
     Custom oprg search by publisher_iati_id and sort by publisher_first_published
    """
    model = context['model']
    api = context.get('api_version')
    groups = data_dict.get('groups')
    group_type = data_dict.get('type', 'group')
    ref_group_by = 'id' if api == 2 else 'name'
    pagination_dict = {}
    limit = data_dict.get('limit')
    if limit:
        pagination_dict['limit'] = data_dict['limit']
    offset = data_dict.get('offset')
    if offset:
        pagination_dict['offset'] = data_dict['offset']
    if pagination_dict:
        pagination_dict, errors = _validate(
            data_dict, logic.schema.default_pagination_schema(), context)
        if errors:
            raise ValidationError(errors)
    sort = data_dict.get('sort') or 'title'
    q = data_dict.get('q', '').strip()

    all_fields = asbool(data_dict.get('all_fields', None))

    if all_fields:
        # all_fields is really computationally expensive, so need a tight limit
        max_limit = config.get(
            'ckan.group_and_organization_list_all_fields_max', 50)
    else:
        max_limit = config.get('ckan.group_and_organization_list_max', 1000)

    if bypass_limit_internal and limit:
        max_limit = limit

    if limit is None or limit > max_limit:
        limit = max_limit

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

    sort_info = get_core._unpick_search(sort,
                               allowed_fields=['name', 'packages',
                                               'package_count', 'title', 'publisher_first_publish_date'],
                               total=1)

    if sort_info and sort_info[0][0] == 'package_count':
        query = model.Session.query(model.Group.id,
                                    model.Group.name,
                                    sqlalchemy.func.count(model.Group.id)).join(model.GroupExtra)

        query = query.filter(model.Member.group_id == model.Group.id) \
            .filter(model.Member.table_id == model.Package.id) \
            .filter(model.Member.table_name == 'package') \
            .filter(model.Package.state == 'active')
    else:
        query = model.Session.query(model.Group.id,
                                    model.Group.name).join(model.GroupExtra)

    query = query.filter(_and_(model.Group.state == 'active', model.GroupExtra.key == 'publisher_iati_id'))

    if groups:
        query = query.filter(model.Group.name.in_(groups))
    if q:
        q = u'%{0}%'.format(q)
        query = query.filter(_or_(
            model.Group.name.ilike(q),
            model.Group.title.ilike(q),
            model.GroupExtra.value.ilike(q),
        ))

    query = query.filter(model.Group.is_organization == is_org)
    query = query.filter(model.Group.type == group_type)

    if sort_info:
        sort_field = sort_info[0][0]
        sort_direction = sort_info[0][1]
        if sort_field == 'package_count':
            query = query.group_by(model.Group.id, model.Group.name)
            sort_model_field = sqlalchemy.func.count(model.Group.id)
        elif sort_field == 'name':
            sort_model_field = model.Group.name
        elif sort_field == 'title':
            sort_model_field = model.Group.title
        elif sort_field == "publisher_first_publish_date":
            sort_model_field = model.GroupExtra.value
            query = query.subquery()
            query = model.Session.query(model.Group.id, model.Group.name).join(
                query, query.c.id == model.Group.id).join(model.GroupExtra).filter(
                model.GroupExtra.key == 'publisher_first_publish_date')
        else:
            sort_model_field = model.Group.title

        if sort_direction == 'asc':
            query = query.order_by(sqlalchemy.asc(sort_model_field))
        else:
            query = query.order_by(sqlalchemy.desc(sort_model_field))

    if limit:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)

    groups = query.distinct().all()

    if all_fields:
        action = 'organization_show' if is_org else 'group_show'
        group_list = []
        for group in groups:
            data_dict['id'] = group.id
            for key in ('include_extras', 'include_tags', 'include_users',
                        'include_groups', 'include_followers'):
                if key not in data_dict:
                    data_dict[key] = False

            group_list.append(logic.get_action(action)(context, data_dict))
    else:
        group_list = [getattr(group, ref_group_by) for group in groups]

    return group_list


def _approval_needed(context, data_dict, is_org=False):
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

    sort_info = get_core._unpick_search(sort,
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
    query = query.filter(model.Group.state == 'approval_needed')
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


@p.toolkit.side_effect_free
def organization_list(context, data_dict):
    p.toolkit.check_access('organization_list', context, data_dict)
    data_dict['groups'] = data_dict.pop('organizations', [])
    data_dict.setdefault('type', 'organization')
    return _custom_group_or_org_list(context, data_dict, is_org=True)


@p.toolkit.side_effect_free
def organization_list_pending(context, data_dict):
    p.toolkit.check_access('organization_list', context, data_dict)
    data_dict['groups'] = data_dict.pop('organizations', [])
    data_dict['type'] = 'organization'
    return _approval_needed(context, data_dict, is_org=True)


def user_show(context, data_dict):
    '''
    Return a user account with max. 1000 datasets rather than
    max 50 as in the core `user_show` function (CKAN 2.6.2).

    See the core `user_show` function for full documenentation.

    '''
    log.debug('Overwriting core user_show to increase max. packages in user_dict to 1000')
    model = context['model']

    id = data_dict.get('id', None)
    provided_user = data_dict.get('user_obj', None)
    if id:
        user_obj = model.User.get(id)
        context['user_obj'] = user_obj
        if user_obj is None:
            raise NotFound
    elif provided_user:
        context['user_obj'] = user_obj = provided_user
    else:
        raise NotFound

    p.toolkit.check_access('user_show', context, data_dict)

    # include private and draft datasets?
    requester = context.get('user')
    sysadmin = False
    if requester:
        sysadmin = authz.is_sysadmin(requester)
        requester_looking_at_own_account = requester == user_obj.name
        include_private_and_draft_datasets = (
            sysadmin or requester_looking_at_own_account)
    else:
        include_private_and_draft_datasets = False
    context['count_private_and_draft_datasets'] = \
        include_private_and_draft_datasets

    include_password_hash = sysadmin and asbool(
        data_dict.get('include_password_hash', False))

    user_dict = model_dictize.user_dictize(
        user_obj, context, include_password_hash)

    if context.get('return_minimal'):
        log.warning('Use of the "return_minimal" in user_show is '
                    'deprecated.')
        return user_dict

    if asbool(data_dict.get('include_datasets', False)):
        user_dict['datasets'] = []

        fq = "+creator_user_id:{0}".format(user_dict['id'])

        search_dict = {'rows': 1000}  # The only change vs. the core function.

        if include_private_and_draft_datasets:
            search_dict.update({
                'include_private': True,
                'include_drafts': True})

        search_dict.update({'fq': fq})

        user_dict['datasets'] = \
            logic.get_action('package_search')(context=context,
                                               data_dict=search_dict) \
            .get('results')

    if asbool(data_dict.get('include_num_followers', False)):
        user_dict['num_followers'] = logic.get_action('user_follower_count')(
            {'model': model, 'session': model.Session},
            {'id': user_dict['id']})

    return user_dict


def resource_delete(context, data_dict):
    '''Each dataset must have a single resource.
    '''
    return {'msg': 'Each dataset must contain a single resource. Did you mean to use package_delete?'}


@p.toolkit.side_effect_free
def user_list(context, data_dict):
    """
    Functionality: User must be able to reset password through email id or username
    Wrap the core user list by considering the option for user email
    """
    val = data_dict.get('id', '')
    # Check if the given id is email else call core user list.
    if val and hlp.email_validator(val):
        user = []
        users = hlp.get_user_list_by_email(val)
        # Multiple users with same email id
        # In this case we cannot reset because we dont know what user is is.
        if len(users) == 1:
            user = [users[0].__dict__]
        return user

    return get_core.user_list(context, data_dict)


@p.toolkit.side_effect_free
def user_create(context, data_dict):
    """
    Avoid already existing user to create a new user.
    Check if the email id already exists if so raise errors
    """
    _email = data_dict.get('email', '')
    # User form accepts errors in terms of dict with error list
    errors = dict()
    errors['email'] = []
    if hlp.email_validator(_email):
        _users = hlp.get_user_list_by_email(_email)
        if _users:
            errors['email'].append("Email already exists.")
            raise ValidationError(errors)
    else:
        errors['email'].append("Not a valid email.")
        raise ValidationError(errors)
    return create_core.user_create(context, data_dict)

