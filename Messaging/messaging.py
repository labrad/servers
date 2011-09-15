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
name = Messaging Server
version = 1.2
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

import pyle.telecomm.messaging

class EmailServer(LabradServer):
    """Server to send email"""
    name = 'Messaging Server'
    
    def initServer(self):
        print 'initializing server'
    
    @inlineCallbacks
    def stopServer(self):
        pass

    @setting(10, toAddrs=['s','*s'], subject='s', msg='s', username='s', returns='b')
    def send_mail(self, c, toAddrs, subject, msg, username='LabRAD'):
        try:
            pyle.telecomm.messaging.email(toAddrs,subject,msg,username)
            return True
        except:
            return False
            
    @setting(11, subject='s', msg='s', username='s', returns='b')
    def send_sms(self, c, subject, msg, username):
        try:
            pyle.telecomm.messaging.textMessage(username,subject,msg)
            return True
        except:
            return False
    
__server__ = EmailServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
