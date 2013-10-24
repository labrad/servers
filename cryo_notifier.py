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
version = 2.0
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

DEBUG = True

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
    """Start an external server
    
    Use this to make sure dependencies are running, ie the telecom server.
    """
    if server_name in cxn.servers:
        returnValue(True)
    if node_name in cxn.servers:
        p = cxn[node_name].packet()
        p.start(server_name)
        yield p.send()
        returnValue(True)
    raise RuntimeError("Unable to start server %s" % server_name)

class CryoNotifier(LabradServer):
    """Mass email when someone forgets to fill cryos
    
    Todo: subclass DeviceServer and allow multiple notifyer devices per server.
    This is a real problem. There are several places in this server at which we
    make LabRAD calls to device servers without explicitly stating which device
    we'd like to talk to. For example, we ask the lakeshore diode controller
    for temperature data after a selectDevice() call with no arguments. This
    means we get whatever the first lakeshare diode box on our LabRAD network
    happens to be.
    """
    name = 'Cryo Notifier'
    
    def temperatureCheckFunc(self, channel, temp):
        try:
            #pylabrad units are more broke than Ted on a Thursday night. You
            #can't do comparison without first going to float in a common unit.
            return temp['K'] > self.temperatureBounds[channel]['K']
        except KeyError:
            print("Channel %s has no bound, unable to check"%channel)
            return False
    
    @inlineCallbacks
    def initServer(self):
        self.sent_notifications = set()
        self.cold = False
        self.reg = self.client.registry
        self.ruox = self.client.lakeshore_ruox
        self.diodes = self.client.lakeshore_diodes
        #type of parameter -> {'data'->data, 'func'->func to check if notification needed}
        self.thingsToCheck = {"timers":
                                 {"data": None,
                                  "func": lambda channel, x: x<0},
                              "temperatures":
                                 {"data": None,
                                  "func": self.temperatureCheckFunc}}
        self.path = ['', 'Servers', self.name]
        yield start_server(self.client, 'node_vince', 'Telecomm Server')
        self.cb = LoopingCall(self.checkForAndSendAlerts)
        self.cb.start(interval=10.0, now=True)
        
    @setting(5, returns='*(sv[s])') 
    def query_timers(self, c):
        '''
        Returns the list of timers and their time remaining. Expired
        timers will have a negative time remaining.  If timing is
        disabled all timers will list zero.
        '''
        if self.enabled:
            yield self.loadRegistryInfo()
            yield self.update_timers()
            rv = self.thingsToCheck["timers"]["data"]
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
                p.set('%s_count' % timer_name, rv['get'] + 1)
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
            yield self.loadRegistryInfo()
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
    def loadRegistryInfo(self):
        p = self.reg.packet()
        p.cd(self.path)
        p.get('temperatures', key='temperatures')
        p.get('timers', key='timers') #List of timers for all fridges
        p.get('timers_enabled', key='enabled') #global bool
        p.get('notify_users', key='users') #List of who receives notifications
        p.get('notify_email', False, [], key='email') #...and their emails.
        ans = yield p.send()
        
        self.users = ans['users']
        self.email = ans['email']
        self.enabled = ans['enabled']
        self.timerSettings = dict(ans['timers'])
        self.temperatureBounds = dict(ans['temperatures'])
    
    @inlineCallbacks
    def update_temperatures(self):
        #Check to see if we're still cold
        try:
            p = self.client.lakeshore_diodes.packet()
            p.select_device()
            p.temperatures()
            ans = yield p.send()
            self.cold = ans['temperatures'][1]['K'] < 10.0
        except Exception:
            #Assume we are cold if we can't reach the lakeshore server
            self.cold = True
        p = self.ruox.packet()
        p.select_device(key='device') #This is BAD. We should actually pick a device
        p.named_temperatures(key='temps')
        resp = yield p.send()
        data = dict([(x[0],x[1][0]) for x in resp['temps']])
        nodeName = resp['device'].split(' ')[0]
        #Now we do something really ugly. We need to be able to handle the fact
        #that the temperature bound data in the registry comes with cryostat
        #names attached, eg Vince:Mix1. However the named temperatures from the
        #ruox server come as Mix1, without the cryostat name. To handle this we
        #figure out what _node_ the ruox server is on and add that to the name.
        #This is really pretty bad but I can't think of a good way to fix it.
        #The next person to service this server (heh) can take up where I left
        #off. Upgrade the temperature checking facilities to more rationally
        #sort the data.
        data = dict([(nodeName+':'+k,v) for k,v in data.items()])
        self.thingsToCheck['temperatures']['data'] = data
    
    @inlineCallbacks
    def update_timers(self):
        """Helper function to read timers.
        
        Sets self.currentData["temperatures"] to a dict mapping timer names ->
        remaining time. Remaining times are Values with time units.
        """
        now = datetime.datetime.now()
        p = self.reg.packet()
        for timer_name in self.timerSettings:
            p.get('%s_reset' % timer_name, True, now, key=timer_name)
            p.get('%s_count' % timer_name, False, -1, key=timer_name+"-count")
        ans = yield p.send()
        
        self.timers = {}
        self.counters = {}
        for timer_name in self.timerSettings:
            self.timers[timer_name] = \
                (self.timerSettings[timer_name].inUnitsOf('s'),
                 ans[timer_name])
            self.counters[timer_name] = ans[timer_name+"-count"]
        remaining_time = [(name, (x[0] - td_to_seconds(now-x[1])*s )) \
                              for name, x in self.timers.iteritems()]
        self.thingsToCheck['timers']['data'] = remaining_time
    
    @inlineCallbacks
    def checkForAndSendAlerts(self):
        '''
        Timed callback to check timers and send notifications.
        '''
        yield self.loadRegistryInfo()
        yield self.update_timers()
        yield self.update_temperatures()
        
        if not (self.enabled and self.cold):
            return
        
        for thingToCheck in self.thingsToCheck:
            data = dict(self.thingsToCheck[thingToCheck]['data'])
            thereIsProblem = self.thingsToCheck[thingToCheck]['func']
            alerts = []
            for t in data:
                if thereIsProblem(t, data[t]):
                    if t not in self.sent_notifications:
                        self.sent_notifications.add(t)
                        alerts.append(t)
                    else:
                        pass
                else:
                    self.sent_notifications.discard(t)
        if alerts:
            print "Alerts exist on: ", alerts
            print "Notifying the following users: ", self.users
            #SMS notifications
            yield self.sendSMSNotifications("Cryo Alert", "%s cryos need to be filled." % (alerts,))
            yield self.sendEmailNotifications("Cryo Alert", "%s cryos need to be filled." % (alerts,))
    
    @inlineCallbacks
    def sendEmailNotifications(self, subj, msg):
        """Notify all users via email"""
        try:
            print "sending email notifications to: ", self.email
            if not DEBUG:
                p = self.client.telecomm_server.packet()
                p.send_mail(self.email, subj, msg)
                yield p.send()
        except Exception:
            print "Sending mail to users %s failed" % self.email
    
    @inlineCallbacks
    def sendSMSNotifications(self, subj, msg):
        """Notify all users via SMS"""
        #Try each user separately in case one fails
        print("Sending SMS notifications to %s"%self.users)
        for u in self.users:
            try:
                if not DEBUG:
                    p = self.client.telecomm_server.packet()
                    p.send_sms(subj, msg, u)
                    yield p.send()
            except Exception:
                print("SMS attempt for user %s failed" % u)
    
__server__ = CryoNotifier()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
