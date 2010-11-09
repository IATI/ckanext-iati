from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
import email
import smtplib
import logging
from urlparse import urljoin
from time import time

from ckan.plugins import implements, SingletonPlugin, IGroupController

log = logging.getLogger(__name__)

BODY_TEMPLATE = """
Dear %(admin_name)s, 

the IATI Registry user %(user_name)s just created a new publisher, 
titled "%(group_title)s". In order to become active, it needs to be 
confirmed by an administrator. Please visit the link below and set 
state to 'active' (to approve) or 'deleted' (to disapprove). 

 %(group_link)s
 
Best regards, 

 The IATI Registry
"""

class IatiGroupApprovalExtension(SingletonPlugin):
    implements(IGroupController, inherit=True)
    
    def __init__(self):
        from ckan.model import core
        if not core.State.PENDING in core.State.all:
            log.warning("Adding 'pending' state to vdm State for IATI pubisher approval") 
            core.State.all.append(core.State.PENDING)
    
    def get_admins(self):
        from ckan import model
        q = model.Session.query(model.SystemRole)
        q = q.autoflush(False)
        q = q.filter_by(role=model.Role.ADMIN)
        q = q.filter(model.SystemRole.user!=None)
        return [uor.user for uor in q]
        
    def compose_message(self, group, admin):
        from pylons import config, c
        group_link = urljoin(config.get('ckan.site_url', 'http://iatiregistry.org'), 
                             '/group/' + group.name)
        body_args = {'admin_name': admin.display_name,
                     'user_name': c.author,
                     'group_title': group.title,
                     'group_link': group_link}
        body = BODY_TEMPLATE % body_args
        message = MIMEText(body.encode('utf-8'), 'plain', 'utf-8')
        subject = "[IATI Registry] New Publisher: %s" % group.title
        message['Subject'] = Header(subject.encode('utf-8'), 'utf-8')
        message['Date'] = email.Utils.formatdate(time())
        message['To'] = admin.email
        message['From'] = config.get('iati.email', 'no-reply@iatiregistry.org')
        return message
        
    def notify_admins(self, group):
        from pylons import config
        for admin in self.get_admins():
            if not admin.email: 
                continue
            try:
                message = self.compose_message(group, admin)
                server = smtplib.SMTP(config.get('smtp_server', 'localhost'))
                server.sendmail(message['From'], [admin.email], message.as_string())
                server.quit()
            except Exception, e:
                log.exception(e)
    
    def create(self, group):
        from ckan import model
        from ckan.authz import Authorizer
        from pylons import c 
        if (not c.user) or (not Authorizer.is_sysadmin(c.user)):
            group.state = model.State.PENDING
            self.notify_admins(group)
    