from ckan.controllers.admin import AdminController
import ckan.lib.base as base
import ckan.model as model
import ckan.lib.helpers as h

import logging
log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)

c = base.c
request = base.request
_ = base._


class PurgeController(AdminController):

    """
    Change the core purge controller which is not consistent -
    This is because of the revisions associated with other packages - data inconsistent
    Note: we are not checking any revisions while purge-package. 
    Instead we delete the datasets if it flagged as deleted in database
    """

    def trash(self):
        deleted_revisions = model.Session.query(
            model.Revision).filter_by(state=model.State.DELETED)
        deleted_packages = list(model.Session.query(
            model.Package).filter_by(state=model.State.DELETED))
        msgs = []
        if (u'purge-packages' in request.params) or (
                u'purge-revisions' in request.params):
            if u'purge-packages' in request.params:
                revs_to_purge = []

                pkg_len = len(deleted_packages)

                if pkg_len > 0:
                    for i, pkg in enumerate(deleted_packages, start=1):

                        log.debug('Purging {0}/{1}: {2}'.format(i, pkg_len, pkg.id))
                        members = model.Session.query(model.Member) \
                            .filter(model.Member.table_id == pkg.id) \
                            .filter(model.Member.table_name == 'package')
                        if members.count() > 0:
                            for m in members.all():
                                m.purge()

                        pkg = model.Package.get(pkg.id)
                        model.repo.new_revision()
                        pkg.purge()
                        model.repo.commit_and_remove()
                else:
                    msg = _('No deleted datasets to purge')
                    msgs.append(msg)
            else:
                revs_to_purge = [rev.id for rev in deleted_revisions]
            revs_to_purge = list(set(revs_to_purge))
            for id in revs_to_purge:
                revision = model.Session.query(model.Revision).get(id)
                try:
                    # TODO deleting the head revision corrupts the edit
                    # page Ensure that whatever 'head' pointer is used
                    # gets moved down to the next revision
                    model.repo.purge_revision(revision, leave_record=False)
                except Exception as inst:
                    msg = _(u'Problem purging revision %s: %s') % (id, inst)
                    msgs.append(msg)
            h.flash_success(_(u'Purge complete'))
        else:
            msgs.append(_(u'Action not implemented.'))

        for msg in msgs:
            h.flash_error(msg)
        return h.redirect_to(u'admin.trash')
