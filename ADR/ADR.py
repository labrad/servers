# Copyright (C) 2010  Daniel Sank
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
name = ADR Server
version = 0.33
description =

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

### TODO
#   Nail down error handling during startup
#	misc error handling in some other functions. not a huge deal (i think).
#   PNA functions
#	logic to figure out what status we should be in given peripheral readings on startup


from labrad.devices import DeviceServer, DeviceWrapper
from labrad import types as T, util
from labrad.server import setting
from labrad.units import Unit
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
import twisted.internet.error

import numpy as np
import time, exceptions, labrad.util, labrad.units

#Registry path to ADR configurations
CONFIG_PATH = ['','Servers','ADR']
# 18 Amps is the max, ladies and gentlemen
PS_MAX_CURRENT = 18.8
# if HANDSOFF, don't actually do anything
HANDSOFF = False

class Peripheral(object): #Probably should subclass DeviceWrapper here.
    
    def __init__(self,name,server,ID,ctxt):
        self.name = name
        self.ID = ID
        self.server = server
        self.ctxt = ctxt

    @inlineCallbacks
    def connect(self):
        yield self.server.select_device(self.ID,context=self.ctxt)

class ADRWrapper(DeviceWrapper):

    # INITIALIZATION #

    @inlineCallbacks
    def connect(self, *args, **peripheralDict):
        """     
        TODO: Add error checking and handling
        """
        #Give the ADR a client connection to LabRAD.
        #ADR's use the same connection as the ADR server.
        #Each ADR makes LabRAD requests in its own context.

        self.cxn = args[0]
        self.ctxt = self.cxn.context()
        self._refreshPeripheralLock = False
        # give us a blank log
        self.logData = []
        # initialize the state variables. 
        # many of these will get overwritten with defaults from the registry.
        self.stateVars= {	# FROM THE REGISTRY
                            # magging variables
                            'quenchLimit': 4.0,			# K -- if we get above this temp when magging we are considered to have quenched
                            'cooldownLimit': 3.9,		# K -- below this temp we are ready to rock and roll
                            'rampWaitTime': 0.2,		# s -- min waiting time between voltage ramps (mag steps) during a mag
                            'voltageStepUp': 0.004, 	# V -- voltage ramp amount during mag up
                            'voltageStepDown': 0.004,	# V -- ... during mag down
                            'voltageLimit': 0.28,		# V -- don't do a mag step when mag diode voltages are > this
                            'targetCurrent': 8,			# A -- stop magging when we hit this current (will continue to drift up)
                            'maxCurrent': 9,			# A -- hard limit the power supply to this current
                            'fieldWaitTime': 45,		# min -- how long to wait at field before magging down (when autocontrolled)
                            'autoControl': False,		# whether to auto control the heat switch
                            'switchPosition': 2,		# switch position on the lock in amplifier box
                            'lockinCurrent': 1e-9,      # current being put through Ruox (for use with lockin)
                            'delayHeatSwitchClose': True,   # don't close the heat switch until cold stage temp > 4K stage temp
                            'heatSwitched': False,      # whether we've closed the heat switch for this mag-up. (internal use only)
                            # PID variables
                            'PIDsetTemp': 0.0 * labrad.units.K,		# setTemp is the temperature goal for PID control
                            'PIDcp': 2.0 * labrad.units.V / labrad.units.K,
                            'PIDcd': 70.0 * labrad.units.V * labrad.units.s / labrad.units.K,
                            'PIDci': 2.0,
                            'PIDintLimit': 0.4,
                            'PIDstepTimeout': 5,		# max amount of time we will remain in PID stepping loop
                            # temperature recording variables
                            'recordTemp': False,		# whether we're recording right now
                            'recordingTemp': 250,		# start recording temps below this value
                            'autoRecord': True,			# whether to start recording automatically
                            'tempRecordDelay':	10,		# every X seconds we record temp
                            # NOT FROM REGISTRY
                            'PIDint': 0,
                            'PIDterr': 0,
                            'PIDloopCount': 0,
                            'PIDout': 0,
                            # scheduling variables
                            'schedulingActive': False,				# whether or not we will auto-mag up or down based on schedule.
                            'scheduledMagDownTime': 0,				# time to start magging down
                            'scheduledMagUpTime': 0,				# time to start magging up
                            'magUpCompletedTime': 0,				# time when mag up was completed
                            'magDownCompletedTime': 0,				# time when mag down was completed
                            # temperature recording variables
                            'tempDelayedCall': None,					# will be the twisted IDelayedCall object that the recording cycle is waiting on							
                            'tempDatasetName': None,					# name of the dataset we're currently recording temperature to
                            'datavaultPath': ["", "ADR", self.name],
                            # logging variables
                            'logfile': '%s-log.txt' % self.name,	# the log file
                            'loglimit': 20,							# max # lines held in the log variable (i.e. in memory)
                            'voltages': [0*labrad.units.V]*8,		# will hold the lakeshore 218 voltage readings
                            'temperatures': [0*labrad.units.K]*8,	# ... temperature readings
                            'magVoltage': 0,						# will hold the magnet (power supply) voltage reading
                            'magCurrent': 0,						# ... current reading
                            'compressorStatus': False,				# will hold status of compressor (pumping or not)
                            'compressorTemperatures': [0*labrad.units.K]*4,
                            'compressorPressures': [0*labrad.units.torr]*2,
                            'compressorMotorCurrent': 0*labrad.units.A,
                            'compressorCPUTemperature': 0*labrad.units.K,
                            'missingCriticalPeripheral': True,		# if the lakeshore or magnet goes missing, we need to hold any mag cycles in process
                            'lockinVoltage': None,
                            'useRuoxInterpolation': False,
                            'ruoxTempCutoff': 20*labrad.units.K,
                            # not really used, but you could shut it down this way
                            'alive': False,
                        }
        # different possible statuses
        self.possibleStatuses = ['cooling down', 'ready', 'waiting at field', 'waiting to mag up', 'magging up', 'magging down', 'ready to mag down', 'pid control']
        self.currentStatus = 'cooling down'
        self.sleepTime = 1.0
        # find our peripherals
        yield self.refreshPeripherals()
        # load our defaults from the registry
        yield self.loadDefaultsFromRegistry()
        # listeners
        yield self.registerListeners()
        # go!
        self.log("Initialization completed. Beginning cycle.")
        reactor.callLater(0.1, self.cycle)
        print "cycled"
        self.log('cycled')
    
    @inlineCallbacks
    def registerListeners(self):
        ''' register message listeners to refresh peripherals on device/server connect/disconnects '''
        server_connect = lambda c, (s, payload): self.refreshPeripherals()
        server_disconnect = lambda c, (s, payload): self.refreshPeripherals()
        device_connect = lambda c, (s, payload): self.refreshPeripherals()
        device_disconnect = lambda c, (s, payload): self.refreshPeripherals()
        mgr = self.cxn.manager
        self.cxn._cxn.addListener(server_connect, source=mgr.ID, ID=10001)
        self.cxn._cxn.addListener(server_disconnect, source=mgr.ID, ID=10002)
        self.cxn._cxn.addListener(device_connect, source=mgr.ID, ID=10003)
        self.cxn._cxn.addListener(device_disconnect, source=mgr.ID, ID=10004)
        yield mgr.subscribe_to_named_message('Server Connect', 10001, True)
        yield mgr.subscribe_to_named_message('Server Disconnect', 10002, True)
        yield mgr.subscribe_to_named_message('GPIB Device Connect', 10003, True)
        yield mgr.subscribe_to_named_message('GPIB Device Disconnect', 10004, True)
    
    @inlineCallbacks
    def loadDefaultsFromRegistry(self):
        reg = self.cxn.registry
        yield reg.cd(CONFIG_PATH, context=self.ctxt)
        dirs = yield reg.dir(context=self.ctxt)
        dirs = dirs[0]
        if self.name + ' defaults' in dirs:
            yield reg.cd(self.name + ' defaults', context=self.ctxt)
        else:
            yield reg.cd("defaults", context=self.ctxt)
        # look for a specific volt to res calibration
        keys = (yield reg.dir(context=self.ctxt))[1]
        if "volt to res %s" % self.name in keys:
            vtrKey = "volt to res %s" % self.name
        else:
            vtrKey = "volt to res"
        # load the vars about ruox calibration (res to temp)
        p = reg.packet(context=self.ctxt)
        p.get("high temp ruox curve", key="htrc")
        p.get("low temp ruox curve", key="ltrc")
        p.get("resistance cutoff", key="rescut")
        p.get("ruox channel", key="ruoxchan")
        p.get("ruox coefs high", key="rch")
        p.get("ruox coefs low", key="rcl")
        p.get(vtrKey, key="vtr")
        if 'interpolation data' in keys:
            p.get('interpolation data', key='iData')
        ans = yield p.send()
        self.state('ruoxCoefsHigh', map(lambda x: x.value, ans.rch))
        self.state('ruoxCoefsLow', map(lambda x: x.value, ans.rcl))
        self.state('highTempRuoxCurve', lambda r, p: eval(ans.htrc))
        self.state('lowTempRuoxCurve', lambda r, p: eval(ans.ltrc))
        self.state('voltToResCalibs', map(lambda x: x.value, ans.vtr))
        self.state('resistanceCutoff', ans.rescut.value)
        self.state('ruoxChannel', ans.ruoxchan - 1)
        if 'interpolation data' in keys:
            iPath, iName = ans.iData
            self.loadInterpolator(iPath, iName)
        # now do the state variables
        yield reg.cd("state variables", context=self.ctxt)
        (dirs, keys) = yield reg.dir(context=self.ctxt)
        for key in keys:
            val = yield reg.get(key, context=self.ctxt)
            if isinstance(val, labrad.units.Value):
                val = val.value
            self.state(key, val)
    
    @inlineCallbacks
    def loadInterpolator(self, dsPath, dsName):
        ''' Using RvsT data from the data vault, construct an interpolating function.
        Requires scipy!'''
        from scipy.interpolate import InterpolatedUnivariateSpline as IUS
        ctx = self.cxn.data_vault.context()
        p = self.cxn.data_vault.packet(context=ctx)
        p.cd(dsPath)
        p.open(dsName)
        p.get(-1, True)
        resp = yield p.send()
        d = resp.get.asarray[::-1]
        f = IUS(d[:,1], d[:,0], k=3)
        self.state('ruoxInterpolation', f)
        self.state('useRuoxInterpolation', True)
    
    ##############################
    # STATE MANAGEMENT FUNCTIONS #
    ##############################
    
    # (these are the functions that do stuff) #
    
    @inlineCallbacks
    def cycle(self):
        """
        this function should get called after the server finishes connecting. it doesn't return.
        each of the statuses will have a sleep for a given amount of time (usually 1s or rampWaitTime).
        """
        self.state('alive', True)
        self.log("Now cycling.")
        lastTime = time.time()
        while self.state('alive'):
            try:
                if not self.cxn._cxn.connected:
                    self.log('LabRAD connection lost.')
                    self.state('alive', False)
                    break
                # also todo: have a little error message thing that can be displayed in the GUI status bar
                # send requests to the lakeshore, magnet, and compressor servers
                lakeshoreResponse = None
                magnetResponse = None
                compressorResponse = None
                lockinResponse = None
                if 'lakeshore' in self.peripheralsConnected.keys():
                    lakeshorePacket = self.peripheralsConnected['lakeshore'].server.packet(context=self.ctxt)
                    lakeshorePacket.voltages()
                    lakeshorePacket.temperatures()
                    lakeshoreResponse = lakeshorePacket.send()
                if 'magnet' in self.peripheralsConnected.keys():
                    magnetPacket = self.peripheralsConnected['magnet'].server.packet(context=self.ctxt)
                    magnetPacket.voltage()
                    magnetPacket.current()
                    magnetResponse = magnetPacket.send()
                if 'compressor' in self.peripheralsConnected.keys():
                    compressorPacket = self.peripheralsConnected['compressor'].server.packet(context=self.ctxt)
                    compressorPacket.status()
                    compressorPacket.temperatures()
                    compressorPacket.pressures()
                    compressorPacket.cpu_temp()
                    compressorPacket.motor_current()
                    compressorResponse = compressorPacket.send()
                if 'temperature_lockin' in self.peripheralsConnected.keys():
                    lockinPacket = self.peripheralsConnected['temperature_lockin'].server.packet(context=self.ctxt)
                    lockinPacket.auto_sensitivity()
                    lockinPacket.r()
                    lockinResponse = lockinPacket.send()
                # process the responses
                if lakeshoreResponse:
                    ans = yield lakeshoreResponse
                    self.state('voltages', ans['voltages'], False)
                    self.state('temperatures', ans['temperatures'], False)
                else:
                    self.state('voltages', [0*labrad.units.V]*8, False)
                    self.state('temperatures', [0*labrad.units.K]*8, False)
                if magnetResponse:
                    ans = yield magnetResponse
                    self.state('magVoltage', ans['voltage'], False)
                    self.state('magCurrent', ans['current'], False)
                else:
                    self.state('magVoltage', 0*labrad.units.V, False)
                    self.state('magCurrent', 0*labrad.units.A, False)					
                if compressorResponse:
                    try:
                        ans = yield compressorResponse
                        self.state('compressorStatus', ans['status'], False)
                        self.state('compressorTemperatures', [x[0] for x in ans['temperatures']], False)
                        self.state('compressorPressures', [x[0] for x in ans['pressures']], False)
                        self.state('compressorCPUTemperature', ans['cpu_temp'], False)
                        self.state('compressorMotorCurrent', ans['motor_current'], False)
                    except Exception as e:
                        self.log("Exception in compressor: %s" % e.__str__())
                else:
                    self.state('compressorStatus', False, False)
                    self.state('compressorTemperatures', [0*labrad.units.K]*4, False)
                    self.state('compressorPressures', [0*labrad.units.torr]*2, False)
                    self.state('compressorCPUTemperature', 0*labrad.units.K, False)
                    self.state('compressorMotorCurrent', 0*labrad.units.A, False)
                if lockinResponse:
                    ans = yield lockinResponse
                    self.state('lockinVoltage', ans['r'], False)
                else:
                    self.state('lockinVoltage', None, False)
                    
                # see how we did
                haveAllPeriphs = (magnetResponse is not None) and (lakeshoreResponse is not None) #(and compressorResponse is not None)
                self.state('missingCriticalPeripheral', not haveAllPeriphs, False)
                
                # check to see if we should start recording temp
                if (not self.state('recordTemp')) and self.state('autoRecord') and self.shouldStartRecording():
                    self.startRecording()

                # now check through the different statuses
                if self.currentStatus == 'cooling down':
                    yield util.wakeupCall(self.sleepTime)
                    # check if we're at base (usually 3.9K), then set status -> ready
                    if self.atBase():
                        self.status('ready')
                                
                elif self.currentStatus == 'ready':
                    yield util.wakeupCall(self.sleepTime)
                    # do we need to cool back down to 3.9K? (i.e. wait)
                    if not self.atBase():
                        self.status('cooling down')
                    # if scheduling is enabled, go to "waiting to mag up":
                    if self.state('schedulingActive'):
                        self.status('waiting to mag up')
                                
                elif self.currentStatus == 'waiting to mag up':
                    yield util.wakeupCall(self.sleepTime)
                    # is scheduling still active?
                    if not self.state('schedulingActive'):
                        self.status('ready')
                    # do we need to cool back down to 3.9K? (i.e. wait)
                    if not self.atBase():
                        self.status('cooling down')
                    # is it time to mag up?
                    if time.time() > self.state('scheduledMagUpTime') and self.atBase():
                        self.status('magging up')
                                
                elif self.currentStatus == 'magging up':
                    self.clear('magDownCompletedTime')
                    self.clear('magUpCompletedTime')
                    self.clear('scheduledMagDownTime')
                    (quenched, targetReached) = yield self.adrMagStep(True) # True = mag step up
                    self.log("%s mag step! Quenched: %s -- Target Reached: %s" % (self.name, quenched, targetReached))
                    if (not self.state('heatSwitched')) and self.state('autoControl') and self.state('delayHeatSwitchClose'):
                        if self.ruoxStatus()[0] >= self.state('temperatures')[1]:
                            self.setHeatSwitch(False)
                            self.state('heatSwitched', True)
                    if quenched:
                        self.log("QUENCHED!")
                        self.status('cooling down')
                    elif targetReached:
                        self.status('waiting at field')
                        self.psMaxCurrent()
                        self.state('magUpCompletedTime', time.time())
                        self.state('scheduledMagDownTime', time.time() + self.state('fieldWaitTime')*60)
                    else:
                        pass # if at first we don't succeed, mag, mag again
                    yield util.wakeupCall(self.state('rampWaitTime'))
                                
                elif self.currentStatus == 'waiting at field':
                    yield util.wakeupCall(self.sleepTime)
                    # is it time to mag down?
                    if time.time() > self.state('scheduledMagDownTime'):
                        if not self.state('schedulingActive'):
                            self.status('ready to mag down')
                        else:
                            self.state('schedulingActive', False)
                            self.status('magging down')
                    
                elif self.currentStatus == 'ready to mag down':
                    yield util.wakeupCall(self.sleepTime)
                        
                elif self.currentStatus == 'magging down':
                    (quenched, targetReached) = yield self.adrMagStep(False)
                    self.log("%s mag step! Quenched: %s -- Target Reached: %s" % (self.name, quenched, targetReached))
                    if quenched:
                        self.log("%s Quenched!" % self.name)
                        self.status('cooling down')
                    elif targetReached:
                        self.status('ready')
                        self.state('magDownCompletedTime', time.time())
                        self.psOutputOff()
                    yield util.wakeupCall(self.state('rampWaitTime'))
                    
                elif self.currentStatus == 'pid control':
                    # try to get to the setTemp state variable with a PID control loop
                    # save old t error
                    terrOld = self.state('PIDterr')
                    # set current t error
                    self.state('PIDterr', self.state('PIDsetTemp') - self.ruoxStatus()[0], False)
                    self.state('PIDint', self.state('PIDint') + self.state('PIDterr')*self.sleepTime, False)
                    if abs(self.state('PIDint')) > self.state('PIDintLimit'):
                        self.state('PIDint', self.state('PIDintLimit')*np.sign(self.state('PIDint')/self.state('PIDci')), False)
                    P = self.state('PIDterr') * self.state('PIDcp')
                    I = self.state('PIDci')*self.state('PIDint')
                    if self.state('PIDloopCount') > 0:
                        D = self.state('PIDcd')*(self.state('PIDterr') - terrOld) / (self.sleepTime)
                    else:
                        D = 0
                    # target voltage
                    self.state('PIDout', self.state('magVoltage') + P + I + D, False)
                    if self.state('PIDout') < 0:
                        self.state('PIDout', 0, False)
                    self.log('PID: T: %.4f  V: %.4f  P: %.4f  I: %.4f  D: %.4f  PID: %.4f' % (self.ruoxStatus()[0], self.state('PIDout'), P, I, D, P+I+D))
                    self.state('PIDloopCount', self.state('PIDloopCount') + 1, False)
                    # now step to it
                    yield self.PIDstep(self.state('PIDout'))
                    yield util.wakeupCall(self.sleepTime)
                    
                else:
                    yield util.wakeupCall(self.sleepTime)
                # end of if (currentStatus)
                lastTime = time.time()
            # end of try
            except KeyboardInterrupt:#, SystemExit):
                self.state('alive', False)
                
            except Exception, e:
                print "Exception in cycle loop: %s" % e.__str__()
                self.log("Exception in cycle loop: %s" % e.__str__())
                yield util.wakeupCall(self.sleepTime)
        # end of while loop
        self.state('alive', False)
            
    
    # these are copied from the LabView program
    # TODO: add error checking
    def atBase(self):
        temps = self.state('temperatures')
        return( (temps[1] < self.state('cooldownLimit')) and (temps[2] < self.state('cooldownLimit')) )
    
    def psMaxCurrent(self):
        """ sets the magnet current to the max current. """
        newCurrent = min(PS_MAX_CURRENT, self.state('maxCurrent'))
        if newCurrent < 0:
            newCurrent = PS_MAX_CURRENT
        magnet = self.peripheralsConnected['magnet']
        if HANDSOFF:
            print "would set %s magnet current -> %s" % (self.name, newCurrent)
            self.log("would set %s magnet current -> %s" % (self.name, newCurrent))
        else:
            self.log("%s magnet current -> %s" % (self.name, newCurrent))
            magnet.server.current(newCurrent, context=magnet.ctxt)
    
    @inlineCallbacks
    def psOutputOff(self):
        """ Turns off the magnet power supply, basically. """
        ps = self.peripheralsConnected['magnet']
        p = ps.server.packet(context=ps.ctxt)
        p.voltage(0)
        p.current(0)
        if HANDSOFF:
            print "would set %s magnet voltage, current -> 0" % self.name
            self.log("would set %s magnet voltage, current -> 0" % self.name)
        else:
            self.log("magnet voltage, current -> 0")
            yield p.send()
        yield util.wakeupCall(0.5)
        if HANDSOFF:
            print "would set %s magnet output_state -> false" % self.name
            self.log("would set magnet output_state -> false")
        else:
            self.log("magnet output_state -> false")
            yield ps.server.output_state(False, context=ps.ctxt)
        
    @inlineCallbacks
    def psOutputOn(self):
        """ Turns on the power supply. """
        ps = self.peripheralsConnected['magnet']
        p = ps.server.packet(context=ps.ctxt)
        newCurrent = min(PS_MAX_CURRENT, self.state('maxCurrent'))
        if newCurrent < 0:
            newCurrent = PS_MAX_CURRENT
        p.current(newCurrent)
        p.output_state(True)
        if HANDSOFF:
            print "would set %s magnet current -> %s\nmagnet output state -> %s" % (self.name, newCurrent, True)
            self.log("would set magnet current -> %s\nmagnet output state -> %s" % (newCurrent, True))
        else:
            self.log("magnet current -> %s\nmagnet output state -> %s" % (newCurrent, True))
            yield p.send()
    
    @inlineCallbacks
    def adrMagStep(self, up):
        """ If up is True, mags up a step. If up is False, mags down a step. """
        # don't mag if we don't have all the peripherals we need!
        if self.state('missingCriticalPeripheral'):
            print "Missing peripheral! Cannot mag! Check lakeshore and magnet!"
            self.log("Missing peripheral! Cannot mag! Check lakeshore and magnet!")
            yield util.wakeupCall(1.0)
            returnValue((False, False))
        temps = self.state('temperatures')
        volts = self.state('voltages')
        current = self.state('magCurrent').value
        voltage = self.state('magVoltage').value
        quenched = temps[1] > self.state('quenchLimit') and current > 0.5
        targetReached = (up and self.state('targetCurrent') - current < 0.001) or (not up and 0.01 > current)
        newVoltage = voltage
        #print "  volts[6]: %s\n  volts[7]: %s\n  voltageLimit: %s" % (volts[6].value, volts[7].value, self.state('voltageLimit'))
        if (not quenched) and (not targetReached) and abs(volts[6]) < self.state('voltageLimit') and abs(volts[7]) < self.state('voltageLimit'):
            #print "changing voltage"
            if up:
                newVoltage += self.state('voltageStepUp')
            else:
                newVoltage -= self.state('voltageStepDown')
        else:
            pass
            #print "not changing voltage"
                        
        if HANDSOFF:
            print "would set %s magnet voltage -> %s" % (self.name, newVoltage)
            self.log("would set %s magnet voltage -> %s" % (self.name, newVoltage))
        else:
            self.log("%s magnet voltage -> %s" % (self.name, newVoltage))
            ps = self.peripheralsConnected['magnet']
            yield ps.server.voltage(newVoltage, context=ps.ctxt)
        returnValue((quenched, targetReached))
        
    @inlineCallbacks
    def PIDstep(self, setV):
        ''' step the magnet to a voltage target. Note that this will repeatedly make small steps in the manner of a mag step. '''
        startTime = time.time()
        doneStepping = False
        while not doneStepping:
            # check current voltages
            ls = self.peripheralsConnected['lakeshore']
            self.state('voltages', (yield ls.server.voltages(context=self.ctxt)), False)
            mag = self.peripheralsConnected['magnet']
            self.state('magVoltage', (yield mag.server.voltage(context=self.ctxt)), False)
            volts = self.state('voltages')
            if abs(volts[6]) < self.state('voltageLimit') and abs(volts[7]) < self.state('voltageLimit'):
                verr = setV - self.state('magVoltage').value
                if abs(verr) > max(self.state('voltageStepUp'), self.state('voltageStepDown')):
                    vnew = self.state('magVoltage') + np.sign(verr) * max(self.state('voltageStepUp'), self.state('voltageStepDown'))
                    yield mag.server.voltage(vnew, context = self.ctxt)
                else:
                    doneStepping = True
                dt = time.time() - startTime
                if dt > self.state('PIDstepTimeout'):
                    doneStepping = True
            yield util.wakeupCall(self.state('rampWaitTime'))
            
    
    @inlineCallbacks
    def setHeatSwitch(self, open):
        """ open the heat switch (when open=True), or close it (when open=False) """
        if 'heatswitch' not in self.peripheralsConnected.keys():
            self.log('cannot open heat switch--server not connected!')
            return
        if open:
            if HANDSOFF:
                print "would open %s heat switch" % self.name
                self.log('would open heat switch')
            else:
                hs = self.peripheralsConnected['heatswitch']
                yield hs.server.open(context=hs.ctxt)
                self.log("open heat switch")
        else:
            if HANDSOFF:
                print "would close %s heat switch" % self.name
                self.log('would close heat switch')
            else:
                hs = self.peripheralsConnected['heatswitch']
                yield hs.server.close(context=hs.ctxt)
                self.log("close heat switch")
    
    def setCompressor(self, start):
        """ if start==true, start compressor. if start==false, stop compressor """
        if start:
            if HANDSOFF:
                print "would start %s compressor" % self.name
                self.log('would start compressor')
            else:
                cp = self.peripheralsConnected['compressor']
                cp.server.start(context=cp.ctxt)
                self.log("start compressor")
        else:
            if HANDSOFF:
                print "would stop %s compressor" % self.name
                self.log('would stop compressor')
            else:
                cp = self.peripheralsConnected['compressor']
                cp.server.stop(context=cp.ctxt)
                self.log("stop compressor")
    
    #########################
    # DATA OUTPUT FUNCTIONS #
    #########################
    
    # getter/setter for state variables
    def state(self, var, newValue = None, log = True):
        if newValue is not None:
            self.stateVars[var] = newValue
            if log:
                self.log('Set %s to %s' % (var, str(newValue)))
            # if we changed the field wait time, we may need to change scheduled mag down time
            if var == 'fieldWaitTime' and self.state('magUpCompletedTime') > 1:
                self.state('scheduledMagDownTime', self.state('magUpCompletedTime') + newValue * 60.0)
            elif var == 'schedulingActive' and newValue:
                self.state('autoControl', True)
        return self.stateVars[var]
        
    # clear a state variable
    def clear(self, var):
        self.stateVars[var] = None
    
    # getter/setter for status
    def status(self, newStatus = None):
        if (newStatus is not None) and (newStatus not in self.possibleStatuses):
            self.log("ERROR: status %s not in possibleStatuses!" % newStatus)
        elif (newStatus is not None) and not (newStatus == self.currentStatus):
            self.currentStatus = newStatus
            if newStatus == 'magging up':
                if self.state('autoControl') and not self.state('delayHeatSwitchClose'):
                    self.state('heatSwitched', True)
                    self.setHeatSwitch(False)
                else:
                    self.state('heatSwitched', False)
                self.psOutputOn()
            elif newStatus == 'magging down':
                if self.state('autoControl'):
                    self.setHeatSwitch(True)
                self.state('schedulingActive', False)
            elif newStatus == 'pid control':
                self.state('PIDout', self.state('magVoltage').value)
                self.state('PIDint', 0)
                self.psOutputOn()
            self.log("ADR %s status is now: %s" % (self.name, self.currentStatus))
            self.state('PIDloopCount', 0)
        return self.currentStatus
    
    # returns the cold stage resistance and temperature
    # interpreted from "RuOx thermometer.vi" LabView program, such as I can
    # the voltage reading is from lakeshore channel 4 (i.e. index 3)
    def ruoxStatus(self):
        lsTemps = self.state('temperatures')
        
        lockin = self.state('lockinVoltage')
        if lockin is None:
            calib = self.state('voltToResCalibs')[self.state('switchPosition') - 1]
            voltage = self.state('voltages')[self.state('ruoxChannel')].value
            resistance = voltage / (calib)* 10**6 # may or may not need this factor of 10^6
        else:
            if lockin.units == 'Ohm':
                resistance = lockin['Ohm']
            else:
                resistance = lockin['V'] / float(self.state('lockinCurrent'))
        if lsTemps[1]['K'] > self.state('ruoxTempCutoff'):
            return (lsTemps[1], resistance)
        temp = 0.0
        if self.state('useRuoxInterpolation'):
            temp = self.state('ruoxInterpolation')(resistance)
        elif resistance < self.state('resistanceCutoff'):
            # high temp (2 to 20 K)
            temp = self.state('highTempRuoxCurve')(resistance, self.state('ruoxCoefsHigh'))
        else:
            # low temp (0.05 to 2 K)
            temp = self.state('lowTempRuoxCurve')(resistance, self.state('ruoxCoefsLow'))
        return (temp, resistance)
            
    ###################################
    # TEMPERATURE RECORDING FUNCTIONS #
    ###################################
    
    # overall plan here:
    # once the temp dips below 250 K, take data every 10 min;
    # in critical periods, do it every 10 s.
    # a "critical period" would be triggered when you start magging up or on user command
    # it would end when the heat switch closes, when temp > (some value), after X hours, or on user command

    def recordTemp(self):
        """
        writes to the data vault.
        independent variable: time
        dependent variables: 50 K temperature (lakeshore 1), 4 K temperature (lakeshore 2), magnet temp (lakeshore 3),
            ruox voltage (lakeshore 4), ruox temp (converted--keep calibration as well?), and power supply V and I
        """
        try:
            dv = self.cxn.data_vault
            if not self.state('tempDatasetName'):
                # we need to create a new dataset
                dv.cd(self.state('datavaultPath'), context=self.ctxt)
                indeps = [('time', 's')]
                deps = [
                        ('temperature', 'ch1: 50K', 'K'),
                        ('temperature', 'ch2: 4K', 'K'),
                        ('temperature', 'ch3: mag', 'K'),
                        ('voltage', 'ch4: ruox', 'V'),
                        ('resistance', 'ruox', 'Ohm'),
                        ('temperature', 'ruox', 'K'),
                        ('voltage', 'magnet', 'V'),
                        ('current', 'magnet', 'Amp'),
                        ('temperature', 'ch5: aux', 'K'),
                        ('temperature', 'CP Water In', 'K'),
                        ('temperature', 'CP Water Out', 'K'),
                        ('temperature', 'CP Helium', 'K'),
                        ('temperature', 'CP Oil', 'K'),
                        ('current', 'CP Motor', 'A'),
                        ('temperature', 'CP CPU', 'K'),
                        ('pressure', 'CP High Side', 'torr'), 
                        ('pressure', 'CP Low Side', 'torr'),
                        ('temperature', 'ch4: ruox (N/A)', 'K'),
                        ('temperature', 'ch6: (N/A)', 'K'),
                        ('temperature', 'ch7: V- (N/A)', 'K'),
                        ('temperature', 'ch8: V+ (N/A)', 'K'),
                        ('voltage', 'ch1: 50K', 'V'),
                        ('voltage', 'ch2: 4K', 'V'),
                        ('voltage', 'ch3: mag', 'V'),
                        ('voltage', 'ch5', 'V'),
                        ('voltage', 'ch6', 'V'),
                        ('voltage', 'ch7: V-', 'V'),
                        ('voltage', 'ch8: V+', 'V'),
                        ]
                name = "ADR Log - %s" % time.strftime("%Y-%m-%d %H:%M")
                dv.new(name, indeps, deps, context=self.ctxt)
                self.state('tempDatasetName', name)
            # assemble the info
            temps = self.state('temperatures')
            volts = self.state('voltages')
            ruox = self.ruoxStatus()
            I, V = (self.state('magCurrent'), self.state('magVoltage'))
            t = int(time.time())
            cpTemps = self.state('compressorTemperatures')
            cpPress = self.state('compressorPressures')
            cpCPU = self.state('compressorCPUTemperature')
            cpMotor = self.state('compressorMotorCurrent')
            # save the data
            dv.add([t, temps[0], temps[1], temps[2], volts[3], ruox[1], ruox[0],
                   V, I, temps[4]] + cpTemps + [cpMotor, cpCPU] + cpPress +
                   [temps[3]] + temps[5:] + volts[0:3] + volts[4:],
                context=self.ctxt)
            # log!
            #self.log("Temperature log recorded: %s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(t)))
        except Exception, e:
            print "Exception in data logging: %s" % e.__str__()
            self.log("Exception in data logging: %s" % e.__str__())
        
    @inlineCallbacks
    def tempCycle(self):
        """
        this function should be called when the temperature recording starts, and will return when it stops.
        it will loop every either 10s or 10 min and then call record temp.
        this also checks each time to see if we should continue recording.
        """
        while self.state('recordTemp'):
            # make the record
            self.recordTemp()

            # check if we should stop recording
            if self.state('autoRecord') and self.shouldStopRecording():
                self.stopRecording()
                break

            d = defer.Deferred()	# we use a blank deferred, so nothing will actually happen when we finish
            e = reactor.callLater(self.state('tempRecordDelay'), d.callback, None)
            self.state('tempDelayedCall', e, False)
            # and now, we wait.
            yield d
            # note that we can interrupt the waiting by messing with the e object (saved in a state variable)
            
    def startRecording(self):
        self.state('recordTemp', True)
        reactor.callLater(0.1, self.tempCycle)
        #self.tempCycle()
    
    def stopRecording(self):
        self.state('recordTemp', False)
        self.state('tempDatasetName', None)
        e = self.state('tempDelayedCall')
        if e:
            try:
                e.reset(0) # reset the counter
            except twisted.internet.error.AlreadyCalled:
                pass
    
    def shouldStartRecording(self):
        """
        determines whether we should start recording.
        """
        temps = self.state('temperatures')
        if len(self.peripheralsConnected.items()) == 0:
            return False
        return temps[0] < self.state('recordingTemp') or temps[1] < self.state('recordingTemp') or self.state('compressorStatus')
        
    def shouldStopRecording(self):
        """
        determines whether to stop recording.
        conditions: temp > 250K, --???
        """
        return not self.shouldStartRecording()

        
        
    #################################
    # PERIPHERAL HANDLING FUNCTIONS #
    #################################
    
    @inlineCallbacks
    def refreshPeripherals(self, refreshGPIB=False):
        while self._refreshPeripheralLock:
            yield util.wakeupCall(0.25)
        self._refreshPeripheralLock = True
        self.allPeripherals = yield self.findPeripherals(refreshGPIB=refreshGPIB)
        print self.allPeripherals
        self.peripheralOrphans = {}
        self.peripheralsConnected = {}
        for peripheralName, idTuple in self.allPeripherals.items():
            yield self.attemptPeripheral((peripheralName, idTuple))
        self._refreshPeripheralLock = False

    @inlineCallbacks
    def findPeripherals(self, refreshGPIB=False):
        """Finds peripheral device definitions for a given ADR (from the registry)
        OUTPUT
            peripheralDict - dictionary {peripheralName:(serverName,identifier)..}
        """
        
        reg = self.cxn.registry
        ctxt = reg.context()
        yield reg.cd(CONFIG_PATH + [self.name], context=ctxt)
        dirs, keys = yield reg.dir(context=ctxt)
        p = reg.packet(context=ctxt)
        for peripheral in keys:
            p.get(peripheral, key=peripheral)
        ans = yield p.send(context=ctxt)
        peripheralDict = {}
        for peripheral in keys: #all key names in this directory
            peripheralDict[peripheral] = ans[peripheral]
        # pomalley 2013-01-25 -- refresh the GPIB bus when we do this
        # pomalley 2013-02-21 -- do it conditionally
        if refreshGPIB:
            nodeList = [v[1] for v in peripheralDict.itervalues()]
            deferredList = []
            for node in set(nodeList):
                for serverName, server in self.cxn.servers.iteritems():
                    if serverName.lower().startswith(node.lower()) and 'gpib' in serverName.lower():
                        deferredList.append(server.refresh_devices())
                        print "refreshing %s" % serverName
            for d in deferredList:
                yield d
        returnValue(peripheralDict)

    @inlineCallbacks
    def attemptOrphans(self):
        for peripheralName, idTuple in self.peripheralOrphans.items():
            yield self.attemptPeripheral((peripheralName, idTuple))

    @inlineCallbacks
    def attemptPeripheral(self,peripheralTuple):
        """
        Attempts to connect to a specified peripheral. If the peripheral's server exists and
        the desired peripheral is known to that server, then the peripheral is selected in
        this ADR's context. Otherwise the peripheral is added to the list of orphans.
        
        INPUTS:
        peripheralTuple - (peripheralName,(serverName,peripheralIdentifier))
        (Note that peripherialIdentifier can either be the full name (e.g. "Kimble GPIB Bus - GPIB0::5")
        or just the node name (e.g. "Kimble")).
        """
        peripheralName = peripheralTuple[0]
        serverName = peripheralTuple[1][0]
        peripheralID = peripheralTuple[1][1]
        #If the peripheral's server exists, get it,
        if serverName in self.cxn.servers:
            server = self.cxn.servers[serverName]
        #otherwise orphan this peripheral and tell the user.
        else:
            self._orphanPeripheral(peripheralTuple)
            print 'Server ' + serverName + ' does not exist.'
            print 'Check that the server is running and refresh this ADR'
            return

        # If the peripheral's server has this peripheral, select it in this ADR's context.
        devices = yield server.list_devices()
        if peripheralID in [device[1] for device in devices]:
            yield self._connectPeripheral(server, peripheralTuple)
        # if we couldn't find the peripheral directly, check to see if the node name matches
        # (i.e. if the beginnings of the strings match)
        elif peripheralID in [device[1][0:len(peripheralID)] for device in devices]:
            # find the (first) device that matches
            for device in devices:
                if peripheralID == device[1][0:len(peripheralID)]:
                    # connect it
                    #print "Connecting to %s for %s" % (device
                    yield self._connectPeripheral(server, (peripheralName, (serverName, device[1])))
                    # don't connect more than one!
                    break
        # otherwise, orphan it
        else:
            print 'Server '+ serverName + ' does not have device ' + peripheralID
            self._orphanPeripheral(peripheralTuple)

    @inlineCallbacks
    def _connectPeripheral(self, server, peripheralTuple):
        peripheralName = peripheralTuple[0]
        ID = peripheralTuple[1][1]
        #Make the actual connection to the peripheral device!
        self.peripheralsConnected[peripheralName] = Peripheral(peripheralName,server,ID,self.ctxt)
        yield self.peripheralsConnected[peripheralName].connect()
        print "connected to %s for %s" % (ID, peripheralName)

    def _orphanPeripheral(self,peripheralTuple):
        peripheralName = peripheralTuple[0]
        idTuple = peripheralTuple[1]
        if peripheralName not in self.peripheralOrphans:
            self.peripheralOrphans[peripheralName] = idTuple
    
    #####################
    # LOGGING FUNCTIONS #
    #####################
    
    def log(self, str):
        # write to log file
        try:
            f = open(self.state('logfile'), 'a')
            f.write('%s -- %s\n' % (time.strftime("%Y-%m-%d %H:%M:%S"), str))
        finally:
            f.close()
        # append to log variable
        self.logData.append((time.strftime("%Y-%m-%d %H:%M:%S"), str))
        # check to truncate log to last X entries
        if len(self.logData) > self.state('loglimit'):
            self.logData = self.logData[-self.state('loglimit'):]
    
    def getLog(self):
        return self.logData
        
    def getEntireLog(self):
        s = ''
        f = open(self.state('logfile'))
        s = f.read()
        f.close()
        return s
    
# (end of ADRWrapper)

######################################
########## ADR SERVER CLASS ##########
######################################

class ADRServer(DeviceServer):
    name = 'ADR Server'
    deviceName = 'ADR'
    deviceWrapper = ADRWrapper
    
    #def initServer(self):
    #	return DeviceServer.initServer(self)
    
    #def stopServer(self):
    #	return DeviceServer.stopServer(self)

    @inlineCallbacks
    def findDevices(self):
        """Finds all ADR configurations in the registry at CONFIG_PATH and returns a list of (ADR_name,(),peripheralDictionary).
        INPUTS - none
        OUTPUT - List of (ADRName,(connectionObject,context),peripheralDict) tuples.
        """
        deviceList=[]
        reg = self.client.registry
        yield reg.cd(CONFIG_PATH)
        resp = yield reg.dir()
        ADRNames = resp[0].aslist
        for name in ADRNames:
            if 'defaults' not in name:
                # all required nodes must be present to create this device
                yield reg.cd(name)
                devs = yield reg.dir()
                devs = devs[1].aslist
                missingNodes = []
                for dev in devs:
                    node = yield reg.get(dev)
                    node = node[1].split(' ')[0]
                    if "node_" + node.lower() not in self.client.servers:
                        missingNodes.append(node)
                if not missingNodes:
                    deviceList.append((name,(self.client,)))
                else:
                    print "device %s missing nodes %s" % (name, str(set(missingNodes)))
                yield reg.cd(1)                
            
        returnValue(deviceList)

    @setting(211, 'refresh gpib')
    def refresh_gpib(self, c):
        '''Refreshes all relevant GPIB buses and then looks for peripherals.'''
        dev = self.selectedDevice(c)
        yield dev.refreshPeripherals(refreshGPIB=True)

    @setting(21, 'refresh peripherals', returns=[''])
    def refresh_peripherals(self,c):
        """Refreshes peripheral connections for the currently selected ADR"""

        dev = self.selectedDevice(c)
        yield dev.refreshPeripherals()

    @setting(22, 'list all peripherals', returns='*?')
    def list_all_peripherals(self,c):
        dev = self.selectedDevice(c)
        peripheralList=[]
        for peripheral,idTuple in dev.allPeripherals.items():
            peripheralList.append((peripheral,idTuple))
        return peripheralList

    @setting(23, 'list connected peripherals', returns='*?')
    def list_connected_peripherals(self,c):
        dev = self.selectedDevice(c)
        connected=[]
        for name, peripheral in dev.peripheralsConnected.items():
            connected.append((peripheral.name,peripheral.ID))
        return connected

    @setting(24, 'list orphans', returns='*?')
    def list_orphans(self,c):
        dev = self.selectedDevice(c)
        orphans=[]
        for peripheral,idTuple in dev.peripheralOrphans.items():
            orphans.append((peripheral,idTuple))
        return orphans

    @setting(32, 'echo PNA', data=['?'], returns=['?'])
    def echo_PNA(self,c,data):
        dev = self.selectedDevice(c) #this gets the selected ADR
        if 'PNA' in dev.peripheralsConnected.keys():
            PNA = dev.peripheralsConnected['PNA']
            resp = yield PNA.server.echo(data, context=PNA.ctxt)
            returnValue(resp)
    
    @setting(40, 'Voltages', returns=['*v[V]'])
    def voltages(self, c):
        """ Returns the voltages from this ADR's lakeshore diode server. """
        dev = self.selectedDevice(c)
        return dev.state('voltages')
    
    @setting(41, 'Temperatures', returns=['*v[K]'])
    def temperatures(self, c):
        """ Returns the temperatures from this ADR's lakeshore diode server. """
        dev = self.selectedDevice(c)
        return dev.state('temperatures')
            
    @setting(42, 'Magnet Status', returns=['(v[V] v[A])'])
    def magnet_status(self, c):
        """ Returns the voltage and current from the magnet power supply. """
        dev = self.selectedDevice(c)
        return (dev.state('magCurrent'), dev.state('magVoltage'))
            
    @setting(43, 'Compressor Status', returns=['b'])
    def compressor_status(self, c):
        """ Returns True if the compressor is running, false otherwise. """
        dev = self.selectedDevice(c)
        return (dev.state('compressorStatus'))
            
    @setting(44, 'Ruox Status', returns=['(v[K] v[Ohm])'])
    def ruox_status(self, c):
        """ Returns the temperature and resistance measured at the cold stage. """
        dev = self.selectedDevice(c)
        return dev.ruoxStatus()
        
    @setting(45, 'Set Compressor', value='b')
    def set_compressor(self, c, value):
        """ True starts the compressor, False stops it. """
        dev = self.selectedDevice(c)
        dev.setCompressor(value)
        
    @setting(46, 'Set Heat Switch', value='b')
    def set_heat_switch(self, c, value):
        """ 
        True opens the heat switch, False closes it.
        There is no confirmation! Don't fuck up.
        """
        dev = self.selectedDevice(c)
        dev.setHeatSwitch(value)
    
    @setting(50, 'List State Variables', returns=['*s'])
    def list_state_variables(self, c):
        """ Returns a list of all the state variables for this ADR. """
        dev = self.selectedDevice(c)
        return dev.stateVars.keys()
    
    @setting(51, 'Set State', variable = 's', value='?')
    def set_state(self, c, variable, value):
        """ Sets the given state variable to the given value. """
        dev = self.selectedDevice(c)
        dev.state(variable, value)
    
    @setting(52, 'Get State', variable = 's', returns=["?"])
    def get_state(self, c, variable):
        """ Gets the value of the given state variable. """
        dev = self.selectedDevice(c)
        return dev.state(variable)
    
    @setting(53, 'Status', returns = ['s'])
    def status(self, c):
        """ Returns the status (e.g. "cooling down", "waiting to mag up", etc.) """
        dev = self.selectedDevice(c)
        return dev.status()
    
    @setting(54, 'List Statuses', returns = ['*s'])
    def list_statuses(self, c):
        """ Returns a list of all allowed statuses. """
        dev = self.selectedDevice(c)
        return dev.possibleStatuses
        
    @setting(55, 'Change Status', value='s')
    def change_status(self, c, value):
        """ Changes the status of the ADR server. """
        dev = self.selectedDevice(c)
        dev.status(value)
        
    @setting(56, "Get Log", returns = ['*(ss)'])
    def get_log(self, c):
        """ Gets this ADR's log. """
        dev = self.selectedDevice(c)
        return dev.getLog()
        
    @setting(57, "Write Log", value='s')
    def write_log(self, c, value):
        """ Writes a single entry to the log. """
        dev = self.selectedDevice(c)
        dev.log(value)
        
    @setting(58, "Revert to Defaults")
    def revert_to_defaults(self, c):
        """ Reverts the state variables to the defaults in the registry. """
        dev = self.selectedDevice(c)
        dev.loadDefaultsFromRegistry()
        
    @setting(59, "Get Entire Log")
    def get_entire_log(self, c):
        ''' Gets the entire log. '''
        dev = self.selectedDevice(c)
        return dev.getEntireLog()
        
    # the 60's settings are for controlling the temp recording
    @setting(60, "Start Recording")
    def start_recording(self, c):
        """ Start recording temp. """
        dev = self.selectedDevice(c)
        dev.state('autoRecord', False)
        dev.startRecording()
    @setting(61, "Stop Recording")
    def stop_recording(self, c):
        """ Stop recording temp. """
        self.selectedDevice(c).stopRecording()
    @setting(62, "Is Recording")
    def is_recording(self, c):
        """ Returns whether recording or not. """
        dev = self.selectedDevice(c)
        return dev.state('recordTemp')
        
    @setting(63, "Mag Step", up='b')
    def mag_step(self, c, up):
        ''' mag step '''
        dev = self.selectedDevice(c)
        dev.adrMagStep(up)
    
__server__ = ADRServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
