#!/usr/bin/python
# Copyright (C) 2013  Evan Jeffrey
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
name = Cryo Notifier
version = 1.0
description = Send reminders to fill cryos

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import Unit, mV, ns, deg, MHz, V, GHz, rad, s
import datetime

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.task import LoopingCall
from twisted.internet.defer import inlineCallbacks, returnValue

'''
Registry keys:

[ "", "Servers", "Cryo Notifier" ]
    timers = [ ("name1", interval[s]), 
                ("name2", interval[s]),
                ("name3", interval[s])]
    name1_reset = timestamp
    notify_users = ["user1, "user2"]
    timers_enabled = True
'''
class CryoNotifier(LabradServer):
    """Mass email when someone forgets to fill cryos"""
    name = 'Cryo Notifier'
    
    @inlineCallbacks
    def initServer(self):
        # Build list of timers from registry
        # Connect to SMS server
        # Get list of allowed users
        self.reg = self.client.registry
        self.sms = self.client.telecomm_server
        try:
            nodename = util.getNodeName()
            path = ['', 'Servers', self.name]
            # try to load for this node
            p = self.reg.packet()
            p.cd(path)
            p.get("timers", key="timers")
            p.get("notify_users", key="users")
            p.get("timers_enabled", key="enabled")
            ans = yield p.send()
            self.timers = dict(ans['timers'])
            self.users = ans['users']
            self.enabled = ans['enabled']
        except:
            print "unable to load setting from registry"
            raise
        self.cb = LoopingCall(self.check_timers)
        self.cb.start(interval=10.0)
    @setting(5, returns='*(s,v[s])')
    def query_timers(self, c):
        if self.enabled:
            rv = yield self.read_timers()
        else:
            rv = [(t, 0) for t in self.timers]
        returnValue(rv)
    @inlineCallbacks
    def read_timers(self):
        rv = []
        p = self.reg.packet()
        for timer_name in self.timers:
            p.get('%s_reset' % timer_name, key=timer_name)
        ans= yield p.send()
        for timer_name in self.timers:
            elapsed = datetime.datetime.now() - ans[timer_name]
            remaining = self.timers[timer_name] - (elapsed.days*(24*3600)+elapsed.seconds)*s
            rv.append((timer_name, remaining))
        returnValue(rv)

    @setting(10, timer_name='s', returns='v[s]')
    def reset_timer(self, c, timer_name):
        if timer_name not in self.timers:
            raise KeyError("Timer %s unknown" % name)
        else:
            p = self.reg.packet()
            p.set("%s_reset" % timer_name, datetime.datetime.now())
            p.send()
            return self.timers[timer_name]

    @setting(15, username='s', returns='b')
    def validate_user(self, c, username):
        # Check to see if user is on list of valid users.
        # If not, but they are known by SMS server, add them
        # to list of users.

        if self.enabled and (username in self.users):
            return True
        else:
            return False
    @setting(20, enable='b')
    def enable_timers(self,c,enable):
        p = self.reg.packet()
        p.set("timers_enabled", enable)
        yield p.send()
        self.enabled = enable
        
    @setting(25, returns='*s')
    def allowed_users(self, c):
        # Return list of users currently enabled for notification.
        # Only these uses can use qubit sequencer
        return self.users

    @inlineCallbacks
    def check_timers(self):
        # Refresh timer list from registry
        # if timer expired, and last notification > 30 min, notify users
        # update last notification
        # email, SMS
        print "Checking timers"
        if not self.enabled:
            print "timers not enabled... skipping"
            return
        timer_list = yield self.read_timers()
        timer_list = dict(timer_list)
        expire_list = []
        for t in timer_list:
            if timer_list[t] < (0*s):
                expire_list.append(t)
        if expire_list:
            print "The following timers have expired: ", expire_list
            print "Notifying the following users: "
            for u in self.users:
                print "        ", u
                try: # We send each SMS individiually in case one address fails
                    p = self.sms.packet()
                    p.send_sms("Cryo Alert", "%s cryos need to be filled." % expire_list, self.users)
                    #yield p.send() Don't send until this is working!
                except:
                    print "Send to user %s failed!"
__server__ = CryoNotifier()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
