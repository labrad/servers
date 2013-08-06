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

def td_to_seconds(td):
    '''
    Takes a timedelta object and returns the time interval in seconds
    '''
    return td.microseconds*1e-6 + td.seconds + td.days * 24.0 * 3600.0

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
@inlineCallbacks
def start_server(cxn, node_name, server_name):
    if server_name in cxn.servers:
        returnValue(True)
    if node_name in cxn.servers:
        p = cxn[node_name].packet()
        p.start(server_name)
        yield p.send()
        returnValue(True)
    raise RuntimeError("Unable to start server %s" % server_name)

class CryoNotifier(LabradServer):
    """Mass email when someone forgets to fill cryos"""
    name = 'Cryo Notifier'

    @inlineCallbacks
    def initServer(self):
        # Build list of timers from registry
        # Connect to SMS server
        # Get list of allowed users
        self.sent_notifications = set()
        self.cold = False

        self.reg = self.client.registry
        self.path = ['', 'Servers', self.name]
        yield start_server(self.client, 'node_vince', 'Telecomm Server')
        self.cb = LoopingCall(self.check_timers)
        self.cb.start(interval=60.0, now=True)
    @setting(5, returns='*(sv[s])') 
    def query_timers(self, c):
        '''
        Returns the list of timers and their time remaining. Expired
        timers will have a negative time remaining.  If timing is
        disabled all timers will list zero.
        '''
        if self.enabled:
            rv = yield self.update_timers()
        else:
            rv = [(t, 0) for t in self.timers]
        returnValue(rv)

    @setting(10, timer_name='s', message='s', returns='v[s]')
    def reset_timer(self, c, timer_name, message=''):
        if timer_name not in self.timers:
            raise KeyError("Timer %s unknown" % name)
        else:
            dt = datetime.datetime.now()
            p = self.reg.packet()
            p.set("%s_reset" % timer_name, dt)
            p.get("%s_count" % timer_name, False, -1)
            p.cd('log')
            p.set(dt.isoformat(), (timer_name, message))
            p.cd(self.path)
            rv = yield p.send()
            counter_val = rv['get']
            if counter_val > -1:
                print('Incrementing counter %s to %d' % (timer_name, counter_val+1))
                p = self.reg.packet()
                p.set('%s_count' % timer_name, rv['get'] +1 )
                yield p.send()
            returnValue(self.timers[timer_name][0])


    @setting(11, name='s', val='w', returns='w')
    def counter(self, c, name, val=None):
        if name not in self.timers:
            raise KeyError("Counter %s unknown" % name)
        p = self.reg.packet()
        if val is not None:
            p.set('%s_count' % name, val)
        p.get('%s_count' % name, False, 0)
        rv = yield p.send()
        returnValue(rv['get'])

    @setting(12, returns='*(s,w)')
    def query_counters(self, c):
        if self.enabled:
             yield self.update_timers()
        rv = self.counters.items()
        returnValue(rv)
        
    @setting(15, username='s', returns='b')
    def validate_user(self, c, username):
        '''
        Check to see if user is on list of valid users.
        If not, but they are known by SMS server, add them
        to list of users.
        '''
        if not self.cold: # Allow anyone when fridge is warm
            return True
        if self.enabled and (username.lower() in [x.lower() for x in self.users]):
            return True
        else:
            return False
    @setting(20, enable='b')
    def enable_timers(self,c,enable):
        '''
        Turn on or off timing.  This should be turned on when the fridge is cold.
        '''
        p = self.reg.packet()
        p.set("timers_enabled", enable)
        yield p.send()
        self.enabled = enable
        
    @setting(25, returns='*s')
    def allowed_users(self, c):
        '''Return list of users currently enabled for notification.
        Only these users should be able to use qubit sequencer.'''
        return self.users

    @inlineCallbacks
    def update_timers(self):
        '''
        Helper function to read timers.
        '''
        rv = []
        try:
            p = self.client.lakeshore_diodes.packet()
            p.select_device()
            p.temperatures()
            ans = yield p.send()
            self.cold = ans['temperatures'][1]['K'] < 10.0
        except Exception:
            self.cold=True # Assume we are warm if we can't reach the lakeshore server
            
        p = self.reg.packet()
        p.cd(self.path)
        p.get('timers', key='timers')
        p.get('timers_enabled', key='enabled')
        p.get('notify_users', key='users')
        p.get('notify_email', False, [], key='email')
        ans = yield p.send()

        self.users = ans['users']
        self.email = ans['email']
        self.enabled = ans['enabled']
        timer_settings = dict(ans['timers'])

        now = datetime.datetime.now()

        p = self.reg.packet()
        for timer_name in timer_settings:
            p.get('%s_reset' % timer_name, True, now, key=timer_name)
            p.get('%s_count' % timer_name, False, -1, key=timer_name+"-count")
        ans= yield p.send()

        self.timers = {}
        self.counters = {}
        for timer_name in timer_settings:
            #print "updating timer %s with value (%s, %s)" % (timer_name, timer_settings[timer_name], ans[timer_name])
            self.timers[timer_name] = (timer_settings[timer_name].inUnitsOf('s'), ans[timer_name])
            self.counters[timer_name] = ans[timer_name+"-count"]
        remaining_time = [ (name, (x[0] - td_to_seconds(now-x[1])*s )) for name, x in self.timers.iteritems() ]
        #print "remaining time:"
        #print remaining_time
        returnValue(remaining_time)
                           
    @inlineCallbacks
    def check_timers(self):
        '''
        Timed callback to check timers and send notifications.
        '''
        # Refresh timer list from registry
        # if timer expired, and last notification > 30 min, notify users
        # update last notification
        # email, SMS
        timer_list = yield self.update_timers()
        #print "Checking timers"
        if not (self.enabled and self.cold):
            # print "timers not enabled or cryostat hot... skipping"
            return

        timer_list = dict(timer_list)
        expire_list = []
        for t in timer_list:
            if timer_list[t] < (0*s):
                #print "timer %s expired" % t
                if t not in self.sent_notifications:
                    self.sent_notifications.add(t)
                    expire_list.append(t)
                else:
                    #print "Notification for %s already sent" % t
                    pass
            else:
                #print "timer %s ok" % t
                self.sent_notifications.discard(t)
        if expire_list:
            print "The following timers have expired: ", expire_list
            print "Notifying the following users: ", self.users
            for u in self.users:
                try: # We send each SMS individiually in case one address fails
                    p = self.client.telecomm_server.packet()
                    p.send_sms("Cryo Alert", "%s cryos need to be filled." % (expire_list,), u)
                    yield p.send() 
                except Exception:
                    print "Send to user %s failed!"
            try:
                p = self.client.telecomm_server.packet()
                print "sending email notifications to: ", self.email
                p.send_mail(self.email, "Cryo Alert", "%s cryos need to be filled." % (expire_list,))
                yield p.send()
            except Exception:
                print "Sending email to users %s failed" % self.email
__server__ = CryoNotifier()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
