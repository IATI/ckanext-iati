import logging
import ckan.model as model

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