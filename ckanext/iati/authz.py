import logging
import ckan.model as model
from ckan import signals
from ckan.authz import Authorizer

log = logging.getLogger(__name__)

# Authorization extensions 

def validate_authorization_setup():
    log.warn("Running monkey-patched authorization setup")
    
    for role_action in model.Session.query(model.RoleAction).filter_by(
                                                        role=model.Role.READER, 
                                                        action=model.Action.PACKAGE_CREATE):
        model.Session.delete(role_action)
    
    for role_action in model.Session.query(model.RoleAction).filter_by(
                                                        action=model.Action.GROUP_CREATE):
        model.Session.delete(role_action)
    
    model.setup_default_user_roles(model.System())
    
    
model.validate_authorization_setup = validate_authorization_setup



def _get_group_authz_group(group):
    """ For each group, we're adding an authorization group with the same settings 
        that can then be set as the owner for new packages. """
    from pylons import c     
    # synthetic key since groups can be renamed: 
    authz_group_name = "group-%s-authz" % group.id
    authz_group = model.AuthorizationGroup.by_name(authz_group_name)
    if not authz_group: 
        user = model.User.by_name(c.user)
        if not user: 
            raise ValueError()
        authz_group = model.AuthorizationGroup(name=authz_group_name)
        model.Session.add(authz_group)
        model.add_user_to_authorization_group(user, authz_group, model.Role.ADMIN)
        model.add_authorization_group_to_role(authz_group, model.Role.ADMIN, group)
    return authz_group


def _sync_package_groups_to_authz_groups(pkg):
    authz_groups = [_get_group_authz_group(g) for g in pkg.groups]
    q = model.Session.query(model.PackageRole).filter_by(package=pkg)
    for package_role in q.all():
        if package_role.authorized_group is None:
            continue
        keep_role = False
        for authz_group in authz_groups:
            if package_role.authorized_group == authz_groups:
                keep_role = True
                authz_groups.remove(authz_group)
        if not keep_role:
            model.Session.delete(package_role)
    for authz_group in authz_groups:
        pkg_role = model.PackageRole(package=pkg, user=None, authorized_group=authz_group, 
                                     role=model.Role.ADMIN)
        model.Session.add(pkg_role)


def _get_user_authz_groups():
    from pylons import c 
    if not c.user: 
        return []
    return Authorizer.get_authorization_groups(c.user)

def on_package_new(pkg):
    if len(pkg.groups) == 0:
        # invalid for iati, but lets not drop our privs and pants over this. 
        return 
    model.clear_user_roles(pkg, [])
    model.setup_default_user_roles(pkg, [])
    _sync_package_groups_to_authz_groups(pkg)
    
signals.PACKAGE_NEW.connect(on_package_new)

def on_package_edit(pkg):
    if len(pkg.groups) == 0:
        # invalid for iati, but lets not drop our privs and pants over this. 
        return 
    _sync_package_groups_to_authz_groups(pkg)

signals.PACKAGE_EDIT.connect(on_package_edit)

def on_package_delete(pkg):
    pass

signals.PACKAGE_DELETE.connect(on_package_delete)

def on_group_new(group):
    authz_group = _get_group_authz_group(group)  
    
signals.GROUP_NEW.connect(on_group_new)
    
def on_group_edit(group):
    authz_group = _get_group_authz_group(group)

signals.GROUP_EDIT.connect(on_group_edit)
    
def on_group_delete(group):
    authz_group = _get_group_authz_group(group)
    #model.Session.delete(authz_group)
    
signals.GROUP_DELETE.connect(on_group_delete)
    
def on_group_authz_add(group, user_role):
    authz_group = _get_group_authz_group(group)
    model.add_user_to_authorization_group(user_role.user, authz_group, user_role.role)
    
signals.GROUP_AUTHZ_ADD.connect(on_group_authz_add)
    
def on_group_authz_del(group, user_role):
    authz_group = _get_group_authz_group(group)
    model.remove_user_from_authorization_group(user_role.user, authz_group)

signals.GROUP_AUTHZ_DEL.connect(on_group_authz_del)
