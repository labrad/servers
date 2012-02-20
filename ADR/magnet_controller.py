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
version = 0.21
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
Some general comments on the way this server works:
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
import math, time

K, A, V, T = Unit('K'), Unit('A'), Unit('V'), Unit('T')

# hard limits
TEMP_LIMIT = 6.5 * K
CURRENT_LIMIT = 17.17 * A
VOLTAGE_RESOLUTION = 0.0006 * V
VOLTAGE_LIMIT_DEFAULT = 0.1 * V
VOLTAGE_LIMIT_MAX = 0.7 * V
VOLTAGE_LIMIT_MIN = VOLTAGE_RESOLUTION
VOLTAGE_STEP = VOLTAGE_RESOLUTION

CURRENT_RESOLUTION = 0.002 * A

FIELD_CURRENT_RATIO = 0.2823 * T / A
PS_COOLING_TIME = 240   # seconds

# registry and data vault paths
CONFIG_PATH = ['', 'Servers', 'Magnet Controller']
DATA_PATH = ['', 'ADR', 'Magnet Controller']

# servers/devices
POWER = 1       # the main power supply
POWER_SETTINGS = ['current', 'set_current', 'voltage', 'set_voltage']
DMM = 2      # the DMM to monitor magnet voltage
DMM_SETTINGS = ['voltage']
DMM2 = 3
DMM2_SETTINGS = ['current']
DC = 4  # the DC source to heat the persistent switch
DC_SETTINGS = ['current', 'voltage']
TEMPERATURE = 5
TEMPERATURE_SETTINGS = ['temperatures']

SERVERS = {POWER: 'Kepco BOP 20-20', DMM: 'Agilent 34401A DMM', DMM2: 'Agilent 34401A DMM', DC: 'Agilent 3640A DC Source', TEMPERATURE: 'Lakeshore Diodes'}

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
        self.voltageLimit = VOLTAGE_LIMIT_DEFAULT
        self.temperatureOverride = False    # if True, ignore temperature checks
        
        # devices we must link to
        self.devs = OrderedDict()
        self.devs[POWER] = {'server' : None, 'values': [NaN] * len(POWER_SETTINGS), 'status': 'not initialized', 'settings': POWER_SETTINGS, 'extras': ['output']}
        self.devs[DMM] = {'server' : None, 'values': [NaN] * len(DMM_SETTINGS), 'status': 'not initialized', 'settings': DMM_SETTINGS, 'gpib address': 24,}
        self.devs[DC] = {'server' : None, 'values': [NaN] * len(DC_SETTINGS), 'status': 'not initialized', 'settings': DC_SETTINGS, 'extras': ['output', 'persistent_switch_mode', 'persistent_switch_time_elapsed']}
        self.devs[TEMPERATURE] = {'server': None, 'values': [NaN] * len(TEMPERATURE_SETTINGS), 'status': 'not initialized', 'settings': TEMPERATURE_SETTINGS, 'flatten': True, 'pickOneValue': 1}
        self.devs[DMM2] = {'server': None, 'values': [NaN] * len(DMM2_SETTINGS), 'status': 'not initialized', 'settings': DMM2_SETTINGS, 'gpib address': 22,}
        
        
        # Persistent Switch
        self.psHeated = None            # T/F for switch heated or not
        self.psCurrent = NaN * A        # current when switch was cooled/closed
        self.psTime = 0                 # time since switch state was last changed
        self.psRequestedState = None    # None=leave as is, T = heated, F = cooled
        self.psStatus = 'Not started'
        
        # DV logging stuff
        self.dv = None
        self.dvName = None
        self.dvRecordDelay = 5 # record every X seconds
        self.dvLastTimeRecorded = 0
        self.dvStatus = 'Not started'
        
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
                        self.current(self.devs[POWER]['values'][0])
                    # see about a mag
                    #yield self.doMagCycle()
                    self.doMagCycle()
                    self.status = 'OK'
                except Exception as e:
                    print "Exception in main loop: %s" % str(e)
            else:
                # we are over temperature
                # shut down the magnet if it's running
                if self.devs[POWER]['status'] == 'OK' and abs(self.devs[POWER]['values'][0]) > CURRENT_RESOLUTION:
                    self.devs[POWER]['server'].shut_off(context=self.devs[POWER]['context'])
                    self.current(0*A)
                self.status = 'Over Temperature'
        try:
            # record data
            self.doDataVault()
        except Exception as e:
            print "Exception in data vault"
        try:
            # persistent switch
            self.doPersistentSwitch()
        except Exception as e:
            print "Exception in persistent switch"
            
    @inlineCallbacks
    def doDevice(self, dev):
        # do we need a server? if so, connect to it
        if not self.devs[dev]['server'] and dev in self.cxn.servers:
            self.devs[dev]['server'] = self.cxn[SERVERS[dev]]
            self.devs[dev]['context'] = self.devs[dev]['server'].context()
        # do we have a server? if so, get our data
        if self.devs[dev]['server']:
            # build packet out of requested settings
            p = self.devs[dev]['server'].packet()
            for s in self.devs[dev]['settings']:
                p[s](key=s)
            if 'extras' in self.devs[dev].keys():
                for s in self.devs[dev]['extras']:
                    p[s](key=s)
            try:
                # try to get our data
                ans = yield p.send(context = self.devs[dev]['context'])
                self.devs[dev]['values'] = [ans[s] for s in self.devs[dev]['settings']]
                # couple of special cases
                if 'flatten' in self.devs[dev].keys():
                    self.devs[dev]['values'] = [item for sublist in self.devs[dev]['values'] for item in sublist]
                if 'pickOneValue' in self.devs[dev].keys():
                    self.devs[dev]['values'] = [self.devs[dev]['values'][self.devs[dev]['pickOneValue']]]
                if 'pickSubset' in self.devs[dev].keys():
                    self.devs[dev]['values'] = [self.devs[dev]['values'][x] for x in self.devs[dev]['pickSubset']]
                if 'extras' in self.devs[dev].keys():
                    self.devs[dev]['extraValues'] = [ans[s] for s in self.devs[dev]['extras']]
                self.devs[dev]['status'] = 'OK'
            except Error as e:
                # catch labrad error (usually DeviceNotSelectedError) -- select our device if we have one
                self.devs[dev]['values'] = [NaN] * len(self.devs[dev]['settings'])
                if 'DeviceNotSelectedError' in e.msg or 'NoDevicesAvailableError' in e.msg:
                    print 1
                    devs = yield self.devs[dev]['server'].list_devices(context = self.devs[dev]['context'])
                    found = False
                    for d in devs:
                        if 'gpib address' in self.devs[dev].keys():
                            print d[1]
                            if not d[1].endswith(str(self.devs[dev]['gpib address'])):
                                continue
                        if self.nodeName.upper() in d[1].upper():
                            print 2
                            found = True
                            yield self.devs[dev]['server'].select_device(d[0], context = self.devs[dev]['context'])
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

#    @inlineCallbacks
    def doMagCycle(self):
        ''' Do a mag cycle if applicable. Here are the rules:
        -- Must have connection to all servers, below temperature. (status = OK)
        -- Must be below voltage limit.
        -- Current difference must be larger than the resolution limit.
        '''
        if self.status != 'OK':
            return
        if self.psStatus.startswith('Cooled'):
            self.doMagCycleSwitchCooled()
        elif not self.psStatus.startswith('Heated'):
            return
        if self.devs[POWER]['extraValues'][0] == False:
            self.devs[POWER]['server'].voltage_mode(context=self.devs[POWER]['context'])
            self.devs[POWER]['server'].output(True, context=self.devs[POWER]['context'])
        # is the set current where we want it to be?
        if self.devs[POWER]['values'][1] < abs(self.setCurrent):
            self.devs[POWER]['server'].set_current(abs(self.setCurrent), context=self.devs[POWER]['context'])
        # if the supply setpoint is above the server setpoint
        # and the supply value is below the supply setpoint
        # then set the supply setpoint to max(supply value, server setpoint)
        # (prevents us from leaving the supply setpoint at some high number when magging down)
        print self.devs[POWER]['values'][1], self.setCurrent, self.devs[POWER]['values'][0]
        if self.devs[POWER]['values'][1] > abs(self.setCurrent) + CURRENT_RESOLUTION:
            if abs(self.devs[POWER]['values'][0]) < self.devs[POWER]['values'][1]:
                newcurr = max(abs(self.devs[POWER]['values'][0])+ CURRENT_RESOLUTION*100, abs(self.setCurrent))
                self.devs[POWER]['server'].set_current(newcurr, context=self.devs[POWER]['context'])
        # have we reached the target?
        if abs(self.devs[POWER]['values'][0] - self.setCurrent) < CURRENT_RESOLUTION:
            # set the voltage so that the magnet voltage is zero
            newvolt = self.devs[POWER]['values'][2] - self.devs[DMM]['values'][0]
            self.devs[POWER]['server'].set_voltage(newvolt, context=self.devs[POWER]['context'])
            print 'done magging! %s' % newvolt
            return
        # is the magnet voltage below the limit?
        if self.setCurrent < self.devs[POWER]['values'][0] and self.devs[DMM]['values'][0] > -self.voltageLimit:
            newvolt = self.devs[POWER]['values'][2] - VOLTAGE_STEP
            print "mag step -> %s" % newvolt
            self.devs[POWER]['server'].set_voltage(newvolt, context=self.devs[POWER]['context'])
        elif self.setCurrent > self.devs[POWER]['values'][0] and self.devs[DMM]['values'][0] < self.voltageLimit:
            newvolt = self.devs[POWER]['values'][2] + VOLTAGE_STEP
            print "mag step -> %s" % newvolt
            self.devs[POWER]['server'].set_voltage(newvolt, context=self.devs[POWER]['context'])

    def doMagCycleSwitchCooled(self):
        ''' this is called when the persistent switch is cold. '''
        if abs(self.devs[POWER]['values'][0] - self.setCurrent) < CURRENT_RESOLUTION * 5:
            if abs(self.setCurrent) < CURRENT_RESOLUTION:
                self.devs[POWER]['server'].output(False, context=self.devs[POWER]['context'])
            return
        if self.setCurrent < self.devs[POWER]['values'][0]:
            newvolt = self.devs[POWER]['values'][2] - VOLTAGE_STEP
            self.devs[POWER]['server'].set_voltage(newvolt, context=self.devs[POWER]['context'])
        else:
            newVolt = self.devs[POWER]['values'][2] + VOLTAGE_STEP
            self.devs[POWER]['server'].set_voltage(newvolt, context=self.devs[POWER]['context'])
                
    def doPersistentSwitch(self):
        ''' Handle the persistent switch.
        '''
        # make sure we have the server/device
        if self.devs[DC]['status'] != 'OK':
            self.psStatus = 'No server/device'
            return
        # is DC supply in PS mode?
        if not self.devs[DC]['extraValues'][1]:
            # asynch send message to put in PS Mode
            self.devs[DC]['server'].persistent_switch_mode(True, context=self.devs[DC]['context'])
            self.psStatus = 'Setting PS mode on device.'
            return
        self.psHeated = self.devs[DC]['extraValues'][0]
        self.psTime = self.devs[DC]['extraValues'][2]
        # Logic:
        # if desired state == None, set desired state = current state
        # if desired state == None or desired state == current state == heated, do nothing
        # if desired state == cooled and current state == cooled,
        #   if time > required time, mag to zero
        # if desired state == cooled and current state == heated,
        #   if current value is at setpoint, turn off switch heating, record current value
        # if desired state == heated and current state == cooled,
        #   if current value is not at recorded value, mag to recorded value
        #   if current value is at recorded value, heat switch
        if self.psRequestedState is None:
            self.psRequestedState = self.psHeated
            if not self.psRequestedState:
                self.psCurrent = self.setCurrent
        if self.psRequestedState is True and self.psHeated is True:
            if self.psTime < PS_COOLING_TIME:
                self.psStatus = 'Waiting for heating'
                return
            else:
                self.psStatus = "Heated"
                return
        if self.psRequestedState is False and self.psHeated is False:
            if self.psTime > PS_COOLING_TIME and abs(self.setCurrent) > CURRENT_RESOLUTION:
                self.current(0)
                self.psStatus = 'Cooled; turning off power'
                return
            elif self.psTime > PS_COOLING_TIME and abs(self.devs[POWER]['values'][0]) >= CURRENT_RESOLUTION:
                self.psStatus = 'Cooled; powering down'
                return
            elif self.psTime > PS_COOLING_TIME and abs(self.devs[POWER]['values'][0]) < CURRENT_RESOLUTION:
                self.psStatus = 'Cooled; power off'
                return
            else: # waiting for switch to cool
                self.psStatus = 'Waiting for cooling'
                return
        if self.psRequestedState is False and self.psHeated is True:
            # check for current to be at setpoint
            if abs(self.setCurrent - self.devs[POWER]['values'][0]) < CURRENT_RESOLUTION:
                self.psCurrent = self.devs[POWER]['values'][0]
                self.devs[DC]['server'].output(False, context=self.devs[DC]['context'])   # do the deed, asynch
                self.psStatus = 'Turned heater off'
                return
            else:
                self.psStatus = 'Heated; Waiting for current setpoint'
                return
        if self.psRequestedState is True and self.psHeated is False:
            # ramp to appropriate current
            self.current(self.psCurrent)
            if abs(self.psCurrent - self.devs[POWER]['values'][0]) < CURRENT_RESOLUTION * 5:
                # we're at the appropriate current
                self.devs[DC]['server'].output(True, context=self.devs[DC]['context'])
                self.psStatus = 'Turned heater on'
                return
            else:
                self.psStatus = 'Cooled; Powering up'
                return
        # if we made it here it's a programming error!
        self.psStatus = "Error in code!"
        
    def doDataVault(self):
        ''' Record data if the appropriate time has passed.
        If we need to create a new dataset, do it.
        No need to wait on the return, though. 
        As we do this asynchronously there is a slight danger of one of the add data packets
        arriving ahead of the create dataset packets, but in a practical sense this should
        never happen with the multi-second delay we normally use.'''
        # time, status check
        if (self.status != 'OK' and self.status != 'Over Temperature') or time.time() - self.dvLastTimeRecorded < self.dvRecordDelay:
            return
        self.dvLastTimeRecorded = t = time.time()
        # server check
        if self.dv is None and 'Data Vault' in self.cxn.servers:
            self.dv = self.cxn.data_vault
        elif self.dv is None:
            self.dvStatus = 'Data Vault server not found.'
            return
        # get together our data
        data = [t, self.magnetCurrent(), self.current()]
        for x in self.devs.keys():
            data += self.devs[x]['values']
        p = self.dv.packet(context=self.ctxt)
        # dataset check
        if not self.dvName:
            self.dvName = 'Magnet Controller Log - %s - %s' % (self.nodeName, time.strftime("%Y-%m-%d %H:%M"))
            self.dvNew = True
            p.cd(DATA_PATH, True)
            p.new(self.dvName, ['time [s]'], ['Current (Magnet) [A]', 'Current (Setpoint) [A]', 'Current (Power Supply) [A]', 'Current (Power Supply Setpoint) [A]', 'Voltage (Power Supply) [V]',
                'Voltage (Power Supply Setpoint) [V]', 'Voltage (Magnet) [V]', 'Current (Heater) [A]', 'Voltage (Heater) [V]', 'Temperature (4K) [K]', 'Current (DMM2) [A]'])
            p.add_parameters(('Start Time (str)', time.strftime("%Y-%m-%d %H:%M")), ('Start Time (int)', time.time()))
        # add the data
        p.add(data)
        d = p.send(context=self.ctxt)
        d.addCallback(self.handleDVCreateCallback)
        d.addErrback(self.handleDVError)
        self.dvStatus = 'Logging'

    def handleDVCreateCallback(self, response):
        ''' called after dataset is created. just to get the correct name, really. '''
        if self.dvNew:
            self.dvName = response.new[1]
            self.dvNew = False
            
    def handleDVError(self, failure):
        ''' this is an errback added to the call to the data vault.
        if it gets called (i.e. there is an exception in the DV call),
        we assume that we need to create a data set. '''
        print 'dv error!'
        failure.trap(Error)
        print failure
        self.dvName = None
        self.dv = None
        self.dvStatus = 'Creating new dataset'

    def checkTemperature(self):
        ''' Checks that the magnet temperature is safe. '''
        try:
            #print self.devs[TEMPERATURE]['values'][0]
            good = self.temperatureOverride or self.devs[TEMPERATURE]['values'][0] < TEMP_LIMIT
            return good
        except Exception as e:
            print "Exception in checkTemperature: %s" % e
            return False
            
    def current(self, current=None):
        ''' change the current setpoint. '''
        if current is None:
            return self.setCurrent
        if not isinstance(current, Value):
            current = Value(float(current), 'A')
        self.setCurrent = current.inUnitsOf('A')
        self.setCurrent = max(-CURRENT_LIMIT, min(CURRENT_LIMIT, self.setCurrent))
        return self.setCurrent
        
    def magnetCurrent(self):
        ''' Get the magnet current. This is either the power supply current (if the heater is on)
        or the remembered current if we're in persistent mode. '''
        if self.psHeated is False:
            return self.psCurrent
        else:
            return self.devs[DMM2]['values'][0]
            #return self.devs[POWER]['values'][0]
            
    def getStatus(self):
        ''' returns all the statuses '''
        return [self.status, self.dvStatus, self.psStatus] + [self.devs[dev]['status'] for dev in self.devs.keys()]
            
    def getValues(self):
        ''' returns all the applicable values of this magnet controller. '''
        # a little hackish because we only return the 4K temperature
        r = [self.magnetCurrent(), self.current()]
        for dev in self.devs.keys():
            r += self.devs[dev]['values']
        r.insert(7, self.voltageLimit)
        return r
        #return self.devs[POWER]['values'] + self.devs[DMM]['values'] + self.devs[DC]['values'] + [self.devs[TEMPERATURE]['values'][1]]
        
    def persistentSwitch(self, newState):
        ''' sets/gets the desired state of the switch.
        True = heated = open (leave it this way when magging)
        False = cooled = closed (for steady field)
        Note that the process of opening/closing the switch is an involved one.
        '''
        if newState is not None:
            self.psRequestedState = bool(newState)
        return self.psRequestedState
        
    def psSetCurrent(self, newCurrent):
        if newCurrent is not None:
            if not isinstance(newCurrent, Value):
                newCurrent = Value(float(newCurrent), 'A')
            self.psCurrent = newCurrent.inUnitsOf('A')
            self.psCurrent = max(-CURRENT_LIMIT, min(CURRENT_LIMIT, self.psCurrent))
        return self.psCurrent
        

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
        
    @setting(21, 'Get Values', returns='(v[A] v[A] v[A] v[A] v[V] v[V] v[V] v[V] v[A] v[V] v[K] v[A])')
    def get_values(self, c):
        ''' Returns all the relevant values.\n
        Magnet Current [A], Current Setpoint, PS Current [A], PS Current Setpoint, PS Voltage [V], PS Voltage Setpoint,
        Magnet Voltage [V], Magnet Voltage Setpoint [V], Switch Current [A], Switch Voltage [V], Magnet Temperature [K], Magnet Current 2 [A]'''
        # note: when you change this function keep the comment in the same form - one comma separated label per value
        # on the second line (i.e. after \n)
        return self.selectedDevice(c).getValues()
        
    @setting(22, 'Get Status', returns='(ssssssss)')
    def get_status(self, c):
        ''' Returns all the statuses.\n
        Overall, Data logging, Switch, Power Supply, DMM, DC Source, Temperature, DMM2'''
        # also keep in the same format
        return self.selectedDevice(c).getStatus()
        
    @setting(23, 'Current Setpoint', current='v[A]', returns='v[A]')
    def current_setpoint(self, c, current=None):
        ''' Sets the target current and returns the target current. If there is no argument, only returns the target.\n
            Note that the hard limit on the power supply is just under 15 A, though it will let you set it higher. '''
        return self.selectedDevice(c).current(current)
        
    @setting(24, 'Persistent Switch', newState='b', returns='b')
    def persistent_switch(self, c, newState=None):
        ''' sets/gets the desired state of the switch.
        True = heated = open (leave it this way when magging)
        False = cooled = closed (for steady field)
        Note that the process of opening/closing the switch is an involved one.
        '''
        return self.selectedDevice(c).persistentSwitch(newState)
        
    @setting(25, 'PS Set Current', newCurrent='v[A]', returns='v[A]')
    def ps_set_current(self, c, newCurrent=None):
        ''' Gets what the server remembers the current to be when the persistent switch was cooled.
        This is the value it must mag to when we want to heat the switch again.
        Note that you can modify this (with this function), but do so CAREFULLY!
        Setting heating the switch when the current in the magnet and the current of the supply
        are mismatched is a BAD THING (tm).'''
        return self.selectedDevice(c).psSetCurrent(newCurrent)

    @setting(26, 'Voltage Limit', newLimit='v[V]', returns='v[V]')
    def voltage_limit(self, c, newLimit=None):
        ''' Gets/sets the voltage limit used when magging. Max = 0.7 V, min = 0.01 V.
        This sets how fast we mag. 0.1 is slow, 0.3 is a good speed, anything faster is ZOOM!'''
        if newLimit is not None:
            self.selectedDevice(c).voltageLimit = min(max(newLimit, VOLTAGE_LIMIT_MIN), VOLTAGE_LIMIT_MAX)
        return self.selectedDevice(c).voltageLimit
        
    @setting(30, 'Get Dataset Name', returns='*s')
    def get_dataset_name(self, c):
        ''' returns the path and name of the logging dataset. '''
        dev = self.selectedDevice(c)
        if dev.dvName is None:
            return None
        else:
            return DATA_PATH + [self.selectedDevice(c).dvName]

    @setting(31, 'Get Field', returns='v[T]')
    def get_field(self, c):
        ''' returns the field. (magnet current * field-to-current ratio) '''
        return self.selectedDevice(c).magnetCurrent() * FIELD_CURRENT_RATIO

__server__ = MagnetServer()

if __name__ == '__main__':
	from labrad import util
	util.runServer(__server__)
