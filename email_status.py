import smtplib
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
import os

from Robinhood import Robinhood

home_path = os.path.abspath(os.getcwd())
if 'ec2-user' in home_path:
    home_path = '/home/ec2-user/capit-vita'
par_path = os.path.dirname(home_path) + '/'
home_path = home_path + '/'

with open(os.pardir + '/auth/takaomattpython.txt') as f:
    email_password = f.read()

with open(os.pardir + '/auth/robinhood.txt') as f:
    data = f.read().split('\n')
    RH_username = data[0]
    RH_password = data[1]

my_trader = Robinhood()
my_trader.login(username=RH_username, password=RH_password)
equity = my_trader.equity() + 1200

andrew = .2545
matt = .6187
mazy = .0431
tim = .0836

users = {'matt':['Matt', 0.6187, 'takaomatt@gmail.com'],
    'tim':['Tim', 0.0836, 'takaotim@gmail.com'],
    'mazy':['Mazy', 0.0431, 'mazyyap@gmail.com'],
    'andrew':['Andrew', 0.2545, 'takaoandrew@gmail.com']}

mailing_list = ['takaomatt@gmail.com']

with open(os.pardir + '/auth/takaomattpython.txt') as f:
    password = f.read()

def send_email(name, percent_owned, email_address, equity):
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login('takaomattpython@gmail.com', email_password)

    msg = MIMEMultipart()
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = ': '+str(formatdate(localtime=True))

    # Create the body of the message (a plain-text and an HTML version).
    text = "This is the first test automated email.\n\nHi {}, you own {}% of ${}: ${}".format(name, percent_owned * 100, equity, round(equity * percent_owned, 2))
    text += '\n\nDon\'t worry, I\'ll eventually make this email look fancier.'
    '''
    html = """\
    <html>
      <head></head>
      <body>
        <p>Hi!<br>
           How are you?<br>
           Here is the <a href="https://www.python.org">link</a> you wanted.
        </p>
      </body>
    </html>
    """
    '''

    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    #part2 = MIMEText(html, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    #msg.attach(part2)

    server.sendmail('takaomattpython@gmail.com', email_address, msg.as_string())
    server.quit()
'''
contents = users['matt']
print(contents)
'''

if True:
    users = {'matt':['Matt', 0.6187, 'takaomatt@gmail.com']}

for user in users:
    contents = users[user]
    send_email(contents[0], contents[1], contents[2], equity)
