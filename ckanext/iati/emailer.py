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

    if isinstance(to, basestring):
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
named "{publisher_title}". In order to become active, it needs to be
confirmed by a system administrator. Please visit the link below and set
state to 'active' (to approve) or 'deleted' (to disapprove).

 {publisher_link}

Best regards,

 The IATI Registry
'''

publisher_activation_body_template = '''
Dear {user_name},<br><br>

Congratulations, the publisher that you created on the IATI Registry has been approved.<br><br>

Well done for taking the first step to join over 1500 others in becoming an IATI publisher! Your publisher account can be found in the <a href="{group_link}"> IATI Registry</a>.<br><br>

Your next step is to start creating your IATI files. Guidance for this can be found on the IATI website under step 2 on the <a href="https://iatistandard.org/en/guidance/publishing-data/publishing-files/publishing-checklist/">Publishing Checklist</a>.<br><br>

We are happy to let you know that we have launched the new IATI publishing tool, which will be free to use. 
If you would like to hear more about this please click on the link <a href="https://publisher.iatistandard.org/"/>publisher.iatistandard.org</a><br><br> 

Should you have any queries or support needs, then please email the IATI Helpdesk at: <a href="mailto:support@iatistandard.org">support@iatistandard.org</a><br><br>

You can also join the conversation with other new publishers in the "Newbies Corner" on <a href="https://iaticonnect.org/newbies-corner/stream">IATI Connect</a>.<br><br>


Kind regards,<br>
IATI Technical Team<br>

'''


new_publisher_email_to_publisher_body = '''
Dear {user_name},<br><br>

Thank you for registering with IATI.<br><br>

A member of the Technical Team will review your account and contact you in 1-3 days with an update.<br><br>

Kind regards,<br>
IATI Technical Team<br>
'''

data_published_email_notification_body = '''
Dear {user_name},<br><br>

Congratulations! Your file(s) have been successfully published to <a href="{publisher_link}">IATI</a>.<br><br>

To view your published data, please check <a href="http://d-portal.org/ctrack.html#view=search">d-portal</a> (allow 24 hours after publishing).<br><br>

You can also do a more detailed search of your published data via the <a href="https://iatidatastore.iatistandard.org/querybuilder/">Datastore</a>.<br><br>

Should you have any queries or support needs, then please email the IATI Helpdesk at: <a href="mailto:support@iatistandard.org">support@iatistandard.org</a>.<br><br>

Kind regards,<br>
IATI Technical Team<br>
'''

data_not_xml_email_body = '''
Dear {user_name},<br><br>

You're receiving this email because you are the admin user of {publisher_name}'s IATI Registry account.<br>

We've detected an issue with the following IATI dataset in your IATI Registry account: {publisher_registry_dataset_link}<br>

The dataset is not in a valid IATI XML format. Please see our <a href="https://iatistandard.org/en/guidance/publishing-data/creating-files/">Guidance pages</a> on how to publish your data in IATI XML format.<br>

<br>Should you have any queries or support needs, then please email the IATI Helpdesk at: <a href='support@iatistandard.org'>support@iatistandard.org</a><br>
Kind regards,<br>
IATI Technical Team<br>
'''

data_has_url_errors = '''
Dear {user_name},<br><br>

You're receiving this email because you are the admin user of {publisher_name}'s IATI Registry account.<br>

We've detected an issue with the following IATI dataset in your IATI Registry account: {publisher_registry_dataset_link}<br>

The dataset is not accessible. To fix the error, please update the dataset link (URL) in the IATI Registry.<br>

<br>Should you have any queries or support needs, then please email the IATI Helpdesk at: <a href='support@iatistandard.org'>support@iatistandard.org</a><br>
Kind regards,<br>
IATI Technical Team<br>
'''

dataset_critical_or_error_email = '''
Dear {user_name},<br><br>

You're receiving this email because you published the following dataset to the {publisher_name}'s IATI Registry account: 
<a href="{publisher_registry_dataset_link}">{publisher_registry_dataset_link}</a><br><br>

We've detected that the dataset fails validation and its validation status is {validation_status}.<br><br>

{status_message}<br><br>

Should you have any queries or support needs, then please email the IATI Helpdesk at: support@iatistandard.org<br><br>

Kind regards,<br>
IATI Technical Team 
'''
