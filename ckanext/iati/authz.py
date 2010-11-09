import logging
import ckan.model as model
from ckan import signals
from ckan.authz import Authorizer

from ckan.plugins import implements, SingletonPlugin, IGroupController, IPackageController

log = logging.getLogger(__name__)


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
        model.add_authorization_group_to_role(authz_group, model.Role.EDITOR, group)
    return authz_group


class IatiPackageAuthzExtension(SingletonPlugin):
    implements(IPackageController, inherit=True)
    
    @classmethod
    def _sync_authz_groups(cls, pkg):
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
                                         role=model.Role.EDITOR)
            model.Session.add(pkg_role)


    def create(self, package):
        if len(package.groups) == 0:
            # invalid for iati, but lets not drop our privs and pants over this. 
            return 
        model.clear_user_roles(package)
        model.setup_default_user_roles(package, [])
        self._sync_authz_groups(package)
  
    def edit(self, package):
        if len(package.groups) == 0:
            # invalid for iati, but lets not drop our privs and pants over this. 
            return 
        self._sync_authz_groups(package)


class IatiGroupAuthzExtension(SingletonPlugin):
    implements(IGroupController, inherit=True)
    
    @classmethod
    def _sync_packages(cls, group):
        for package in group.packages:
            IatiPackageAuthzExtension._sync_authz_groups(package)
    
    def create(self, group):
        model.clear_user_roles(group)
        _get_group_authz_group(group)  
        self._sync_packages(group)
    
    def edit(self, group):
        _get_group_authz_group(group)
        self._sync_packages(group)

    def delete(self, group):
        _get_group_authz_group(group)
        self._sync_packages(group)

    def authz_add_role(self, group_role):
        authz_group = _get_group_authz_group(group_role.group)
        if group_role.user:
            model.add_user_to_authorization_group(group_role.user, authz_group, group_role.role)
    
    def authz_remove_role(group, group_role):
        authz_group = _get_group_authz_group(group_role.group)
        if group_role.user and model.user_in_authorization_group(group_role.user, authz_group):
            model.remove_user_from_authorization_group(group_role.user, authz_group)
