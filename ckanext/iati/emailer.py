import logging
import smtplib
from socket import error as socket_error
from email.mime.text import MIMEText

from ckan.plugins.toolkit import config


log = logging.getLogger(__name__)

FROM = config.get('smtp.mail.from', 'no-reply@iatiregistry.org')
SMTP_SERVER = config.get('smtp.server', 'localhost')
#SMTP_USER = config.get('smtp.user', 'username')
#SMTP_PASSWORD = config.get('smtp.password', 'password')

def send_email(content, subject, to, from_=FROM):

    msg = MIMEText(content,'plain','UTF-8')

    if isinstance(to, basestring):
        to = [to]

    msg['Subject'] = subject
    msg['From'] = from_
    msg['To'] = ','.join(to)

    try:
        s = smtplib.SMTP(SMTP_SERVER)
 #       s.login(SMTP_USER, SMTP_PASSWORD)
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

Well done for taking the first step to join over 1300 others in becoming an IATI publisher!
{group_link}

Your next step is to start creating your IATI files. Guidance for this can be found on the IATI website under step 2:
https://iatistandard.org/en/guidance/publishing-data/publishing-files/publishing-checklist/

Should you have any queries or support needs, then please email the IATI Helpdesk at:support@iatistandard.org

You can also join the conversation with other new publishers in the "Newbies Corner" on IATI Connect:
https://iaticonnect.org/newbies-corner/stream


Kind regards,
IATI Technical Team

'''


