# Copyright (C) 2012 Peter O'Malley
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
name = Magnet Controller
version = 0.1
description =

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

'''
Some general comments on the way this servers works:
-- It is a collection of other servers. These servers are the Kepco power supply, Agilent 34401A DMM, and the Agilent 3640A DC source.
-- Other servers may be added: Lakeshore 218 for temperature monitoring.
-- On connecting to the powers supply for the first time, we must set our setpoint to the power supply setpoint so as not to interrupt.
-- On connecting to the DC supply, we must put it into persistent switch mode
-- It has a main loop function that is called repeatedly (ideally every 0.2s, but practically as fast as GPIB communications will allow.
-- It should automatically take care of finding and maintaining connections to the relevant servers.
-- Control of the magnet current/field should be simple: you say go to current/field X, it mags to X.
-- It must check all of the parameters for compliance: max/min current, ramp rate, temperature, etc.
-- If, at any point, the temperature is above 6.5 K (to be safe), the power supply is immediately set to zero.
-- It should record data automatically, with an easy "start a new dataset" feature.
-- It reports all of its statuses in one function, and all of its measurements in another.
'''

import labrad
from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import setting
from labrad.types import Error
from labrad.units import Unit, Value

from twisted.internet.task import LoopingCall
from twisted.internet.defer import inlineCallbacks, returnValue

from OrderedDict import OrderedDict # if we ever go to 2.7 we can use collections.OrderedDict
import math

K, A, V, T = Unit('K'), Unit('A'), Unit('V'), Unit('T')

# hard limits
TEMP_LIMIT = 6.5 * K
CURRENT_LIMIT = 17.17 * A
VOLTAGE_LIMIT = 0.75 * V
CURRENT_STEP = 0.3 * A
CURRENT_RESOLUTION = 0.01 * A
FIELD_CURRENT_RATIO = 0.2823 * T / A

# registry and data vault paths
CONFIG_PATH = ['', 'Servers', 'Magnet Controller']
DATA_PATH = ['', 'Magnet Controller']

# servers/devices
POWER = 'Kepco BOP 20-20'       # the main power supply
POWER_SETTINGS = ['current', 'set_current', 'voltage', 'set_voltage']
DMM = 'Agilent 34401A DMM'      # the DMM to monitor magnet voltage
DMM_SETTINGS = ['voltage']
DC = 'Agilent 3640A DC Source'  # the DC source to heat the persistent switch
DC_SETTINGS = ['current', 'voltage']
TEMPERATURE = 'Lakeshore Diodes'
TEMPERATURE_SETTINGS = ['temperatures']

NaN = float('nan')

def sign(x):
    return cmp(x, 0)

class MagnetWrapper(DeviceWrapper):

    def connect(self, nodeName, cxn):
        print 'Connect: %s' % nodeName
        self.cxn = cxn
        self.ctxt = self.cxn.context()
        self.nodeName = nodeName
        
        # state variables of this object
        self.status = 'Missing Devices'
        self.setCurrent = Value(NaN, 'A')
        self.temperatureOverride = False    # if True, ignore temperature checks
        
        # devices we must link to
        self.devs = OrderedDict()
        self.devs[POWER] = {'server' : None, 'values': [NaN] * len(POWER_SETTINGS), 'status': 'not initialized', 'settings': POWER_SETTINGS}
        self.devs[DMM] = {'server' : None, 'values': [NaN] * len(DMM_SETTINGS), 'status': 'not initialized', 'settings': DMM_SETTINGS}
        self.devs[DC] = {'server' : None, 'values': [NaN] * len(DC_SETTINGS), 'status': 'not initialized', 'settings': DC_SETTINGS}
        self.devs[TEMPERATURE] = {'server': None, 'values': [NaN] * len(TEMPERATURE_SETTINGS), 'status': 'not initialized', 'settings': TEMPERATURE_SETTINGS, 'flatten': True, 'pickOneValue': 1}
        
        # the main loop stuff
        self.timeInterval = 0.2
        self.loop = LoopingCall(self.mainLoop)
        self.loopDone = self.loop.start(self.timeInterval, now=True)
        print 'loop started'
        
    @inlineCallbacks
    def shutdown(self):
        self.loop.stop()
        yield self.loopDone
        
    @inlineCallbacks
    def mainLoop(self):
        #print 'loop executing'
        # do our updates asynch
        defers = [self.doDevice(dev) for dev in self.devs.keys()]
        for defer in defers:
            yield defer
        # do we have all devices?
        if not('OK' == self.devs[POWER]['status'] and 'OK' == self.devs[DMM]['status'] and 'OK' == self.devs[DC]['status'] and 'OK' == self.devs[TEMPERATURE]['status']):
            # if not, update status, do nothing
            self.status = 'Missing Devices'
        else:
            # if so, do stuff
            # check the temperature
            if self.checkTemperature():
                try:
                    # if we don't have a current setpoint, set it to the setpoint of the power supply
                    if math.isnan(self.setCurrent) and self.devs[POWER]['status'] == 'OK':
                        self.current(self.devs[POWER]['values'][1])
                    # see about a mag
                    yield self.doMagCycle()
                    self.status = 'OK'
                except Exception as e:
                    print "Exception in main loop: %s" % str(e)
            else:
                # we are over temperature
                # shut down the magnet if it's running
                if self.devs[POWER]['status'] == 'OK' and abs(self.devs[POWER]['values'][0]) > CURRENT_RESOLUTION:
                    self.devs[POWER]['server'].shut_off()
                    self.current(0*A)
                self.status = 'Over Temperature'
            
    @inlineCallbacks
    def doDevice(self, dev):
        # do we need a server? if so, connect to it
        if not self.devs[dev]['server'] and dev in self.cxn.servers:
            self.devs[dev]['server'] = self.cxn[dev]
        # do we have a server? if so, get our data
        if self.devs[dev]['server']:
            # build packet out of requested settings
            p = self.devs[dev]['server'].packet(context = self.ctxt)
            for s in self.devs[dev]['settings']:
                p[s](key=s)
            try:
                # try to get our data
                ans = yield p.send(context = self.ctxt)
                self.devs[dev]['values'] = [ans[s] for s in self.devs[dev]['settings']]
                # couple of special cases
                if 'flatten' in self.devs[dev].keys():
                    self.devs[dev]['values'] = [item for sublist in self.devs[dev]['values'] for item in sublist]
                if 'pickOneValue' in self.devs[dev].keys():
                    self.devs[dev]['values'] = [self.devs[dev]['values'][self.devs[dev]['pickOneValue']]]
                self.devs[dev]['status'] = 'OK'
            except Error as e:
                # catch labrad error (usually DeviceNotSelectedError) -- select our device if we have one
                self.devs[dev]['values'] = [NaN] * len(self.devs[dev]['settings'])
                if 'DeviceNotSelectedError' in e.msg or 'NoDevicesAvailableError' in e.msg:
                    devs = yield self.devs[dev]['server'].list_devices(context=self.ctxt)
                    found = False
                    for d in devs:
                        if self.nodeName.upper() in d[1].upper():
                            found = True
                            yield self.devs[dev]['server'].select_device(d[0], context=self.ctxt)
                            self.devs[dev]['status'] = 'Found Device'
                    if not found:
                        self.devs[dev]['status'] = 'No Device'
                elif 'Target' in e.msg and 'unknown' in e.msg:
                    # server has been turned off
                    self.devs[dev]['server'] = None
                    self.devs[dev]['status'] = 'No Server'
                else:
                    print 'Unhandled error in main loop: %s' % e.msg
                    self.devs[dev]['status'] = 'Other Error'
        else:
            self.devs[dev]['status'] = 'No Server'
            self.devs[dev]['values'] = [NaN] * len(self.devs[dev]['settings'])

    @inlineCallbacks
    def doMagCycle(self):
        ''' Do a mag cycle if applicable. Here are the rules:
        -- Must have connection to all servers, below temperature. (status = OK)
        -- Must be below voltage limit.
        -- Current difference must be larger than the resolution limit.
        '''
        if self.status != 'OK':
            return
        if not self.checkVoltage():
            return
        diff = self.setCurrent - self.devs[POWER]['values'][0]
        if abs(diff) < CURRENT_RESOLUTION:
            return
        amount = min(abs(diff), CURRENT_STEP) * sign(diff)
        yield self.devs[POWER]['server'].set_current(self.devs[POWER]['values'][0] + amount, context=self.ctxt)
        print 'mag step -> %s' % (self.devs[POWER]['values'][0] + amount)

    def checkTemperature(self):
        ''' Checks that the magnet temperature is safe. '''
        try:
            #print self.devs[TEMPERATURE]['values'][0]
            good = self.temperatureOverride or self.devs[TEMPERATURE]['values'][0] < TEMP_LIMIT
            return good
        except Exception as e:
            print "Exception in checkTemperature: %s" % e
            return False
    
    def checkVoltage(self):
        ''' Checks that the voltage is below the limit. '''
        return abs(self.devs[DMM]['values'][0]) < VOLTAGE_LIMIT
            
    def current(self, current):
        ''' change the current setpoint. '''
        if current is None:
            return self.setCurrent
        if not isinstance(current, Value):
            current = Value(float(current), 'A')
        self.setCurrent = current.inUnitsOf('A')
        self.setCurrent = max(-CURRENT_LIMIT, min(CURRENT_LIMIT, self.setCurrent))
        return self.setCurrent
            
    def getStatus(self):
        ''' returns all the statuses '''
        return [self.status] + [self.devs[dev]['status'] for dev in self.devs.keys()]
            
    def getValues(self):
        ''' returns all the applicable values of this magnet controller. '''
        # a little hackish because we only return the 4K temperature
        r = []
        for dev in self.devs.keys():
            r += self.devs[dev]['values']
        return r
        #return self.devs[POWER]['values'] + self.devs[DMM]['values'] + self.devs[DC]['values'] + [self.devs[TEMPERATURE]['values'][1]]

class MagnetServer(DeviceServer):
    name = 'Magnet Controller'
    deviceName = 'Magnet'
    deviceWrapper = MagnetWrapper

    @inlineCallbacks
    def findDevices(self):
        '''
        Finds all magnet configurations in the registry at CONFIG_PATH and returns a list of (name, [args], {kwargs}).
		args, kwargs are used to call the device's connect function
		'''
        devList = []
        regPacket = self.client.registry.packet()
        regPacket.cd(CONFIG_PATH)
        regPacket.dir(key='dirs')
        regAns = yield regPacket.send()
        for name in regAns['dirs'][0]:
            regPacket = self.client.registry.packet()
            regPacket.cd(CONFIG_PATH + [name])
            regPacket.get('Node Name', key='node')
            regAns = yield regPacket.send()
            devList.append((name, (regAns['node'], self.client), {}))
        print devList
        returnValue(devList)
        
    @setting(21, 'Get Values', returns='(v[A] v[A] v[V] v[V] v[V] v[A] v[V] v[K])')
    def get_values(self, c):
        ''' Returns all the relevant values.
        Power supply current, voltage, DMM/magnet voltage, DC source/persistent switch current, voltage, 4K plate temperature '''
        return self.selectedDevice(c).getValues()
        
    @setting(22, 'Get Status', returns='(sssss)')
    def get_status(self, c):
        ''' Returns all the statuses (overall, power supply, DMM, DC source, lakeshore temperatures). '''
        return self.selectedDevice(c).getStatus()
        
    @setting(23, 'Current Setpoint', current='v[A]', returns='v[A]')
    def current_setpoint(self, c, current=None):
        ''' Sets the target current and returns the target current. If there is no argument, only returns the target.\n
            Note that the hard limit on the power supply is just under 15 A, though it will let you set it higher. '''
        return self.selectedDevice(c).current(current)

__server__ = MagnetServer()

if __name__ == '__main__':
	from labrad import util
	util.runServer(__server__)