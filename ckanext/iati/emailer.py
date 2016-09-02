import logging
import smtplib
from socket import error as socket_error
from email.mime.text import MIMEText

from pylons import config


log = logging.getLogger(__name__)

FROM = config.get('iati.email', 'no-reply@iatiregistry.org')
SMTP_SERVER = config.get('smtp.server', 'localhost')
SMTP_USER = config.get('smtp.user', 'username')
SMTP_PASSWORD = config.get('smtp.password', 'password')

def send_email(content, subject, to, from_=FROM):

    msg = MIMEText(content,'plain','UTF-8')

    if isinstance(to, basestring):
        to = [to]

    msg['Subject'] = subject
    msg['From'] = from_
    msg['To'] = ','.join(to)

    try:
        s = smtplib.SMTP(SMTP_SERVER)
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.sendmail(from_, to, msg.as_string())
        s.quit()
    except socket_error:
        log.critical('Could not connect to email server. Have you configured the SMTP settings?')

new_publisher_body_template = '''
Dear {sysadmin_name},

The IATI Registry user {user_name} ({site_url}/user/{user_name}) just created a new publisher,
named "{publisher_title}". In order to become active, it needs to be
confirmed by a system administrator. Please visit the link below and set
state to 'active' (to approve) or 'deleted' (to disapprove).

 {publisher_link}

Best regards,

 The IATI Registry
'''

publisher_activation_body_template = '''
Dear {user_name},

Congratulations, the publisher that you created on the IATI Registry ({group_title}) has been approved.

 {group_link}

Please ensure that the details published for this record are correct and informative, as the IATI community rely on this information.

You can also start adding data to the Registry in the form of packages that link to IATI data.

Individual files can be added via: {site_url}/dataset/new
Multiple files can be added via a CSV upload function: {site_url}/csv/upload
An API is also available for more technical access: {site_url}/registry-api

Should you have any queries or support need, then please consult the IATI community which includes knowledge base articles and the ability to ask questions of the support team: http://support.iatistandard.org


Best regards,

The International Aid Transparency (IATI) Team


About this email: this email was sent to {user_email} as it has been associated with the IATI Registry publisher {group_title}.  If you think this was mistaken, please contact support@iatistandard.org

'''


