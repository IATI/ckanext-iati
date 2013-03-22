import smtplib

from email.mime.text import MIMEText

from pylons import config

FROM = config.get('iati.email', 'no-reply@iatiregistry.org')
SMTP_SERVER = config.get('smtp_server', 'localhost')

def send_email(content, subject, to , from_=FROM):

    msg = MIMEText(content,'plain','UTF-8')

    if isinstance(to, basestring):
        to = [to]

    msg['Subject'] = subject
    msg['From'] = from_
    msg['To'] = ','.join(to)

    s = smtplib.SMTP(SMTP_SERVER)
    s.sendmail(from_, to, msg.as_string())
    s.quit()
