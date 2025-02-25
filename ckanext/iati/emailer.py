import logging
import smtplib
from socket import error as socket_error
from email.mime.text import MIMEText

from ckan.plugins.toolkit import config


log = logging.getLogger(__name__)

FROM = config.get('smtp.mail.from', 'no-reply@iatiregistry.org')
SMTP_SERVER = config.get('smtp.server', 'localhost')
SMTP_USER = config.get('smtp.user', 'username')
SMTP_PASSWORD = config.get('smtp.password', 'password')

def send_email(content, subject, to, from_=FROM, content_type="plain"):

    msg = MIMEText(content, content_type, 'UTF-8')

    if isinstance(to, str):
        to = [to]

    msg['Subject'] = subject
    msg['From'] = from_
    msg['To'] = ','.join(to)
    try:
        s = smtplib.SMTP(SMTP_SERVER)
        s.starttls()
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.sendmail(from_, to, msg.as_string())
        s.quit()
    except socket_error:
        log.critical('Could not connect to email server. Have you configured the SMTP settings?')

new_publisher_body_template = '''
Dear {sysadmin_name},

The IATI Registry user {user_name} ({site_url}/user/{user_name}) just created a new publisher,
named "{publisher_title}". To become active, it needs to be
confirmed by a system administrator. Please visit the link below and set
state to 'active' (to approve) or 'deleted' (to disapprove).

{publisher_link}

Best regards,

The IATI Registry
'''

new_publisher_email_to_publisher_body = '''
Dear {user_name},<br><br>

Thank you for registering with IATI.<br><br>

We will review your account and contact you within two working days with an update.<br><br>

Kind regards,<br>
IATI Support<br>
'''

data_published_email_notification_body = '''
Dear {user_name},<br><br>

Congratulations! Your file(s) have been successfully published to <a href="{publisher_link}">IATI</a>.<br><br>

To view your published data, please check <a href="http://d-portal.org/ctrack.html#view=search">d-portal</a> (allow 24 hours after publishing).<br><br>

You can also do a more detailed search of your published data via the <a href="https://datastore.iatistandard.org">Datastore</a>.<br><br>

Should you have any queries or support needs, then please email the IATI Helpdesk at: <a href="mailto:support@iatistandard.org">support@iatistandard.org</a>.<br><br>

Kind regards,<br>
IATI Support<br>
'''
