# Copyright (C) 2011  Daniel Sank
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
### BEGIN NODE INFO
[info]
name = Telecomm Server
version = 1.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, util
from labrad.server import LabradServer, setting, Signal
from labrad.types import Error

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

import smtplib

SMS_PATH = ['Servers','Telecomm','sms_users']

def textMessage(recipients, subject, msg, username='LabRAD',attempts=2):
    """Send a text message to one or more recipients

    INPUTS:
    recipients - str or [str,str...]: List of names of labmembers
    to whom you want to send the message. These names must be in the
    SMS_GATEWAYS dictionary.
    subject - str: Subject of the message
    msg - str: message to send
    username - str, optional: PCS account name to stick on the message. Defaults to 'LabRAD'
    """
    if not isinstance(recipients,list):
        recipients = [recipients]
    try:
        email(recipients, subject, msg, username,attempts=attempts)
    except:
        print 'Text message failed'
        raise

def email(toAddrs,subject,msg,username='LabRAD',attempts=2,noisy=False):
    """Send an email to one or more recipients

    INPUTS:
    toAddrs - str or [str...]: target address or list of target addresses
    subject - str: Subject of the message
    msg - str: message to send
    username - str, optional: PCS account name to stick on the message. Defaults to 'LabRAD'
    """
    fromAddr = username+'@physics.ucsb.edu'
    if not isinstance(toAddrs,list):
        toAddrs = [toAddrs]
    header = """From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n"""%(fromAddr,", ".join(toAddrs), subject)
    message = header+msg
    if noisy:
        print 'Sending message:\r\n-------------------------\r\n'+message+'\r\n-------------------------\r\n'
        print '\n'
    for attempt in range(attempts):
        try:
            print 'Sending message from %s' %fromAddr
            server = smtplib.SMTP('smtp.physics.ucsb.edu')
            server.sendmail(fromAddr, toAddrs, message)
            print 'Message sent'
            server.quit()
            break
        except Exception:
            print 'Attempt %d failed. Message not sent' %(attempt+1)
            if attempt<attempts-1:
                print 'Trying again. This is attempt %d' %(attempt+2)
                continue
            else:
                print 'Maximum retries reached'
                raise

class TelecommServer(LabradServer):
    """Server to send email and text messages"""
    name = 'Telecomm Server'
    
    @inlineCallbacks
    def initServer(self):
        print 'initializing server'
        self.sms_users={}
        yield self._refreshSmsUsers()
    
    @inlineCallbacks
    def stopServer(self):
        pass

    @inlineCallbacks
    def _refreshSmsUsers(self):
        cxn = self.client
        reg = cxn.registry
        p = reg.packet()
        p.cd('')
        for d in SMS_PATH[0:-1]:
            p.cd(d)
        p.get(SMS_PATH[-1],key='userlist')
        resp = yield p.send()
        print resp['userlist']
        self.sms_users=dict(resp['userlist'])
        
    @setting(10, toAddrs=['s','*s'], subject='s', msg='s', username='s', returns='b')
    def send_mail(self, c, toAddrs, subject, msg, username='LabRAD'):
        try:
            email(toAddrs,subject,msg,username)
            return True
        except:
            return False
            
    @setting(11, subject='s', msg='s', recipients=['*s','s'], returns='b')
    def send_sms(self, c, subject, msg, recipients):
        if not isinstance(recipients,list):
            recipients = [recipients]
        try:
            recipients = [self.sms_users[name.upper()] for name in recipients]
            print recipients
            textMessage(recipients,subject,msg)
            return True
        except:
            return False

    @setting(20, returns='')
    def refresh(self, c):
        self._refreshSmsUsers()
    
__server__ = TelecommServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
