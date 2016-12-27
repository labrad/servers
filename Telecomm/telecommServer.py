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
version = 1.1
description = 
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

#TODO
#Document input/output values
#Instructions for usage:
#   1) In the registry, create the directory /Servers/Telecomm
#   2) Create a key named 'smsUsers' with value
#       [("USERNAME1","TENDIGITPHONENUMBER@txt.att.net"),...
#       ,("USERNAMEM","TENDIGITPHONENUMBER@vtext.com")]
#      Note that the domain name depends on the user's
#      mobile phone provider. "USERNAME" must be ALL caps.
#   3) Create a key named 'domain' with a value that
#      matches the domain name of the email address
#      from which you wish to send messages.
#      e.g. domain = "physics.someschool.edu"
#   4) Create a key named 'smtpServer' whose value is
#      the smtp server you wish to use.
#   5) (Optional) Create a key named 'password'
#      corresponding to the login credentials of
#      the account you plan to send messages from.
#      Note that some smtp servers require you to
#      authenticate before you can send messages
#      to email addresses outside of its domain.

from labrad import types as T, util
from labrad.server import LabradServer, setting, Signal
from labrad.types import Error

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

import smtplib

REGISTRY_PATH = ['','Servers','Telecomm']
SMS_KEY = 'smsUsers'
DOMAIN_KEY = 'domain'
SERVER_KEY = 'smtpServer'
PASSWORD_KEY = 'password'


def textMessage(recipients, subject, msg, domain, server, username='LabRAD', password=None, attempts=2):
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
    return email(recipients, subject, msg, domain, server, username, password, attempts=attempts)

def email(toAddrs, subject, msg, domain, server, username='LabRAD', password=None, attempts=2, noisy=False):
    """Send an email to one or more recipients
    INPUTS:
    toAddrs - str or [str...]: target address or list of target addresses
    subject - str: Subject of the message
    msg - str: message to send
    username - str, optional: PCS account name to stick on the message. Defaults to 'LabRAD'
    
    RETURNS
    (success, failedList)
    """
    fromAddr = username+'@'+domain
    if not isinstance(toAddrs,list):
        toAddrs = [toAddrs]
    if noisy:
        print 'Sending message:\r\n-------------------------\r\n'+message+'\r\n-------------------------\r\n'
        print '\n'
    for attempt in range(attempts):
        try:
            #Construct message string
            header = """From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n"""%(fromAddr,", ".join(toAddrs), subject)
            message = header+msg
            #Get connection to smtp server and send message
            server = smtplib.SMTP(server)
            if password is not None:
                server.starttls()
                server.login(fromAddr, password)
            result = server.sendmail(fromAddr, toAddrs, message)
            #Update the toAddrs list to include only recipients for which mail sending failed
            toAddrs = result.keys()
            #Messaging was a success, but some recipients may have failed
            return (True, toAddrs)
            
        except Exception:
            print 'Attempt %d failed. Message not sent' %(attempt+1)
            if attempt<attempts-1:
                print 'Trying again. This is attempt %d' %(attempt+2)
                continue
            else:
                print 'Maximum retries reached'
                return (False, toAddrs)

class TelecommServer(LabradServer):
    """Server to send email and text messages"""
    name = 'Telecomm Server'
    
    @inlineCallbacks
    def initServer(self):
        print 'initializing server...'
        self.smsUsers = None
        self.smtpServer = None
        self.domain = None
        yield self._refreshConnectionData()
        print 'initialization complete.'
    
    #@inlineCallbacks # Don't use inlinecallbacks without yield -- ERJ
    def stopServer(self):
        pass
        
    @inlineCallbacks
    def _refreshConnectionData(self):
        print 'Refreshing connection data...'
        cxn = self.client
        reg = cxn.registry
        p = reg.packet()
        p.cd(REGISTRY_PATH)
        p.dir(key = 'regcontent')
        p.get(SMS_KEY, key='userlist')
        p.get(DOMAIN_KEY, key='domain')
        p.get(SERVER_KEY, key='server')
        resp = yield p.send()
        self.smsUsers=dict(resp['userlist'])
        self.domain = resp['domain']
        self.smtpServer = resp['server']
        regContent = resp['regcontent'][1]
        if 'password' in regContent:
            p.get(PASSWORD_KEY, key='password')
            resp = yield p.send()
            self.password = resp['password']
        else:
            self.password = None
        print 'Refresh complete.'
        
    @setting(10, toAddrs=['s{email address of recipient}','*s{array of recipient email addresses}'],
                 subject='s', msg='s', username='s', returns='b{success}*s{failures}')
    def send_mail(self, c, toAddrs, subject, msg, username='LabRAD'):
        success, failures = email(toAddrs, subject, msg, self.domain, self.smtpServer, username, self.password)
        return (success, failures)
            
    @setting(11, subject='s', msg='s', recipients=['*s','s'], username='s', returns='b{success}*s{failures}')
    def send_sms(self, c, subject, msg, recipients, username='LabRAD'):
        if not isinstance(recipients,list):
            recipients = [recipients]
        recipients = [self.smsUsers[name.upper()] for name in recipients if name.upper() in self.smsUsers]
        success, failures = textMessage(recipients, subject, msg, self.domain, self.smtpServer, username, self.password)
        return (success, failures)


    @setting(12, returns='ss')
    def dump_data(self, c):
        return (str(self.domain), str(self.smtpServer))

    @setting(20, returns='')
    def refresh_connection_data(self, c):
        yield self._refreshConnectionData()
    @setting(25, returns='*s')
    def userlist(self, c):
        return self.smsUsers.keys()

__server__ = TelecommServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
