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

# ## TODO
#x clean up init
#x clean up res-temp conversion
#x clean up ruox reading and conversion
#x clean up loggging?
#x review state variables
# fix PID?


import traceback
import time

from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import setting
from labrad.units import Unit
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
import twisted.internet.error
import numpy as np


# ## Globals
# Registry path to ADR configurations
CONFIG_PATH = ['', 'Servers', 'ADR']
# 18 Amps is the max, ladies and gentlemen
PS_MAX_CURRENT = 9.0 * Unit('A')
K, V, s, torr, minutes, A, mA = Unit('K'), Unit('V'), Unit('s'), Unit('torr'), Unit('min'), Unit('A'), Unit('mA')
kOhm, mV = Unit('kOhm'), Unit('mV')


class Peripheral(object):
    def __init__(self, name, server, server_id, context):
        self.name = name
        self.ID = server_id
        self.server = server
        self.ctxt = context

    @inlineCallbacks
    def connect(self):
        yield self.server.select_device(self.ID, context=self.ctxt)


class ADRWrapper(DeviceWrapper):
    # INITIALIZATION #

    # noinspection PyAttributeOutsideInit
    @inlineCallbacks
    def connect(self, *args, **peripheral_dict):
        """     
        TODO: Add error checking and handling
        """
        # Give the ADR a client connection to LabRAD.
        # ADR's use the same connection as the ADR server.
        # Each ADR makes LabRAD requests in its own context.

        self.cxn = args[0]
        self.ctxt = self.cxn.context()
        self._refreshPeripheralLock = False
        # give us a blank log
        self.logData = []
        # initialize the state variables. 
        # any of these can get overwritten with defaults from the registry.
        self.stateVars = {
            # # magging variables ##
            # if we get above this temp when magging we are considered to have quenched
            'quenchLimit': 4.0 * K,
            # base temp for 4K stage
            'cooldownLimit': 3.9 * K,
            # minimum waiting time between voltage ramps (mag steps) during a mag
            'rampWaitTime': 0.2 * s,
            # voltage ramp amount during mag up
            'voltageStepUp': 0.004 * V,
            # ... during mag down
            'voltageStepDown': 0.004 * V,
            # only do mag step if |magnet diode voltage| < voltageLimit
            'voltageLimit': 0.28 * V,
            # stop magging when we hit this current (will continue to drift up)
            'targetCurrent': 8 * A,
            # limit the power supply to this current
            'maxCurrent': 9 * A,
            # how long to wait at field before magging down (when auto-controlled)
            'fieldWaitTime': 45 * minutes,
            # whether to auto control the heat switch
            'autoControl': False,
            # don't close the heat switch until cold stage temp > 4K stage temp
            'delayHeatSwitchClose': True,
            # whether we've closed the heat switch for this mag-up. (internal use only)
            'heatSwitched': False,

            ## ruox measurement ##
            # lakeshore channel to read for ruox voltage (1-8)
            'ruoxChannel': 4,
            # convert from voltage measured by Lakeshore to resistance
            'lockinOhmsPerVolt': 100 * kOhm / V,
            # if true, use interpolation from dataset for temperature. if false, use formula
            'useRuoxInterpolation': False,
            # above this temp, ignore ruox temperature (i.e. use 4K temperature instead)
            'ruoxTempCutoff': 20 * K,
            # for ruox_resistance > resistanceCutoff, use high temp ruox curve, else low temp ruox curve
            'resistanceCutoff': 1.72578 * kOhm,
            # curves and coefficients for above and below the resistanceCutoff
            'lowTempRuoxCurve': '1/(p[0] + p[1]*4*np.log(r) + p[2]*r**2*np.log(r)',
            'ruoxCoefsLow': (-0.77127, 0.00010068, -1.072e-09),
            'highTempRuoxCurve': '1 / (p[0] + p[1] * r**2 * np.log(r) + p[2] * r**3)',
            'ruoxCoefsHigh': (-0.3199412, 5.74884e-08, -8.8409e-11),
            # if we want to use interpolation data instead, set this to (path, dataset)
            # e.g. (['', 'ADR', 'Ruox Calibration'], 8)
            'interpolationData': None,

            ## temperature recording variables ##
            'recordTemp': False,  # whether we're recording right now
            'recordingTemp': 250 * K,  # start recording temps below this value
            'autoRecord': True,  # whether to start recording automatically
            'tempRecordDelay': 10 * s,  # every X seconds we record temp
            'tempDelayedCall': None,  # will be the twisted IDelayedCall object that the recording cycle is waiting on
            'tempDatasetName': None,  # name of the dataset we're currently recording temperature to
            'datavaultPath': ["", "ADR", self.name],

            ## scheduling variables ##
            'schedulingActive': False,  # whether or not we will auto-mag up or down based on schedule.
            'scheduledMagDownTime': 0,  # time to start magging down
            'scheduledMagUpTime': 0,  # time to start magging up
            'magUpCompletedTime': 0,  # time when mag up was completed
            'magDownCompletedTime': 0,  # time when mag down was completed

            ## PID variables ##
            'PIDsetTemp': 0.0 * K,  # setTemp is the temperature goal for PID control
            'PIDcp': 2.0 * V / K,
            'PIDcd': 70.0 * V * s / K,
            'PIDci': 2.0,
            'PIDintLimit': 0.4 * K,
            'PIDstepTimeout': 5 * s,  # max amount of time we will remain in PID stepping loop
            'PIDint': 0,
            'PIDterr': 0,
            'PIDloopCount': 0,
            'PIDout': 0,

            ## logging variables ##
            'logfile': '%s-log.txt' % self.name,  # the log file
            'loglimit': 20,  # max # lines held in the log variable (i.e. in memory)

            ## state tracking variables ##
            'voltages': [0 * V] * 8,  # will hold the lakeshore 218 voltage readings
            'temperatures': [0 * K] * 8,  # ... temperature readings
            'magVoltage': 0,  # will hold the magnet (power supply) voltage reading
            'magCurrent': 0,  # ... current reading
            'compressorStatus': False,  # will hold status of compressor (pumping or not)
            'compressorTemperatures': [0 * K] * 4,  # info about the compressor
            'compressorPressures': [0 * torr] * 2,
            'compressorMotorCurrent': 0 * A,
            'compressorCPUTemperature': 0 * K,
            # if the lakeshore or magnet goes missing, we need to hold any mag cycles in process
            'missingCriticalPeripheral': True,

            # not really used, but you could shut it down this way
            'alive': False,
        }
        # different possible statuses
        self.possibleStatuses = ['cooling down', 'ready', 'waiting at field', 'waiting to mag up', 'magging up',
                                 'magging down', 'ready to mag down', 'pid control']
        self._status = '' 
        self.status = 'cooling down'
        self.sleepTime = 1.0
        # find our peripherals
        yield self.refreshPeripherals()
        # load our defaults from the registry
        yield self.load_defaults_from_registry()
        # listeners
        yield self.register_listeners()
        # go!
        self.log("Initialization completed. Beginning cycle.")
        reactor.callLater(0.1, self.cycle)
        print "started cycling"
        self.log('started cycling')

    @property
    def status(self):
        return self._status

    # noinspection PyAttributeOutsideInit
    @status.setter
    def status(self, new_status):
        print "new_status: %s, _status: %s" % (new_status, self._status)
        if (new_status is not None) and (new_status not in self.possibleStatuses):
            self.log("ERROR: status %s not in possibleStatuses!" % new_status)
        elif (new_status is not None) and not (new_status == self._status):
            self._status = new_status
            if new_status == 'magging up':
                if self.state('autoControl') and not self.state('delayHeatSwitchClose'):
                    self.state('heatSwitched', True)
                    self.set_heat_switch(False)
                else:
                    self.state('heatSwitched', False)
                print "output on"
                self.log("PS output on")
                self.ps_output_on()
            elif new_status == 'magging down':
                if self.state('autoControl'):
                    self.set_heat_switch(True)
                self.state('schedulingActive', False)
            elif new_status == 'pid control':
                self.state('PIDout', self.state('magVoltage'))
                self.state('PIDint', 0)
                self.ps_output_on()
            self.log("ADR %s status is now: %s" % (self.name, self._status))
            self.state('PIDloopCount', 0)

    # noinspection PyProtectedMember
    @inlineCallbacks
    def register_listeners(self):
        """ register message listeners to refresh peripherals on device/server connect/disconnects """
        server_connect = lambda c, (x, payload): self.refreshPeripherals()
        server_disconnect = lambda c, (x, payload): self.refreshPeripherals()
        device_connect = lambda c, (x, payload): self.refreshPeripherals()
        device_disconnect = lambda c, (x, payload): self.refreshPeripherals()
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
    def load_defaults_from_registry(self):
        reg = self.cxn.registry
        yield reg.cd(CONFIG_PATH, context=self.ctxt)
        dirs = yield reg.dir(context=self.ctxt)
        dirs = dirs[0]
        if self.name + ' defaults' in dirs:
            yield reg.cd(self.name + ' defaults', context=self.ctxt)
        else:
            yield reg.cd("defaults", context=self.ctxt)
        # go through all subdirectories and load state vars from registry
        dirs, _ = yield reg.dir(context=self.ctxt)
        for d in dirs:
            print "Loading state variables from subdirectory: %s" % str(d)
            self.log("Loading state variables from subdirectory: %s" % str(d))
            yield reg.cd(d, context=self.ctxt)
            _, keys = yield reg.dir(context=self.ctxt)
            p = reg.packet(context=self.ctxt)
            for k in keys:
                p.get(k, key=k)
            p.cd(1)
            ans = yield p.send()
            for k in keys:
                value = ans[k]
                self.state(k, value, no_new=True)

        try:
            i_path, i_name = self.state('interpolationData')
            inter = yield self.load_interpolator(i_path, i_name)
            self.state('ruoxInterpolation', inter)
            self.state('useRuoxInterpolation', True)
        except KeyError:
            print "Unable to load ruox interpolation."
            pass

    @inlineCallbacks
    def load_interpolator(self, ds_path, ds_name):
        """ Using RvsT data from the data vault, construct an interpolating function.
        Requires scipy!"""
        from scipy.interpolate import InterpolatedUnivariateSpline
        self.log("Loading interpolation data from: %s, dataset: %s" % (ds_path, ds_name))
        ctx = self.cxn.data_vault.context()
        p = self.cxn.data_vault.packet(context=ctx)
        p.cd(ds_path)
        p.open(ds_name)
        p.get()
        resp = yield p.send()
        d = resp.get[::-1]
        f = InterpolatedUnivariateSpline(d[:, 1], d[:, 0], k=3)
        returnValue(f)

    # #############################
    # STATE MANAGEMENT FUNCTIONS #
    # #############################

    # (these are the functions that do stuff) #

    @inlineCallbacks
    def cycle(self):
        """
        this function should get called after the server finishes connecting. it doesn't return.
        each of the statuses will have a sleep for a given amount of time (usually 1s or rampWaitTime).
        """
        self.state('alive', True)
        self.log("Now cycling.")
        while self.state('alive'):
            try:
                if not self.cxn._cxn.connected:
                    self.log('LabRAD connection lost.')
                    self.state('alive', False)
                    break
                # send requests to the lakeshore, magnet, and compressor servers
                lakeshore_response = None
                magnet_response = None
                compressor_response = None
                if 'lakeshore' in self.peripheralsConnected.keys():
                    lakeshore_packet = self.peripheralsConnected['lakeshore'].server.packet(context=self.ctxt)
                    lakeshore_packet.voltages()
                    lakeshore_packet.temperatures()
                    lakeshore_response = lakeshore_packet.send()
                if 'magnet' in self.peripheralsConnected.keys():
                    magnet_packet = self.peripheralsConnected['magnet'].server.packet(context=self.ctxt)
                    magnet_packet.voltage()
                    magnet_packet.current()
                    magnet_response = magnet_packet.send()
                if 'compressor' in self.peripheralsConnected.keys():
                    compressor_packet = self.peripheralsConnected['compressor'].server.packet(context=self.ctxt)
                    compressor_packet.status()
                    compressor_packet.temperatures()
                    compressor_packet.pressures()
                    compressor_packet.cpu_temp()
                    compressor_packet.motor_current()
                    compressor_response = compressor_packet.send()
                # process the responses
                if lakeshore_response:
                    ans = yield lakeshore_response
                    self.state('voltages', ans['voltages'], False)
                    self.state('temperatures', ans['temperatures'], False)
                else:
                    self.state('voltages', [0 * V] * 8, False)
                    self.state('temperatures', [0 * K] * 8, False)
                if magnet_response:
                    ans = yield magnet_response
                    self.state('magVoltage', ans['voltage'], False)
                    self.state('magCurrent', ans['current'], False)
                else:
                    self.state('magVoltage', 0 * V, False)
                    self.state('magCurrent', 0 * A, False)
                if compressor_response:
                    try:
                        ans = yield compressor_response
                        self.state('compressorStatus', ans['status'], False)
                        self.state('compressorTemperatures', [x[0] for x in ans['temperatures']], False)
                        self.state('compressorPressures', [x[0] for x in ans['pressures']], False)
                        self.state('compressorCPUTemperature', ans['cpu_temp'], False)
                        self.state('compressorMotorCurrent', ans['motor_current'], False)
                    except Exception as e:
                        pass
                        #self.log("Exception in compressor: %s" % e.__str__())
                else:
                    self.state('compressorStatus', False, False)
                    self.state('compressorTemperatures', [0 * K] * 4, False)
                    self.state('compressorPressures', [0 * torr] * 2, False)
                    self.state('compressorCPUTemperature', 0 * K, False)
                    self.state('compressorMotorCurrent', 0 * A, False)

                # see how we did
                self.state('missingCriticalPeripheral',
                           magnet_response is None or lakeshore_response is None,
                           False)

                # check to see if we should start recording temp
                if not self.state('recordTemp') and self.state('autoRecord') and self.should_start_recording():
                    self.start_recording()

                # now check through the different statuses
                if self.status == 'cooling down':
                    yield util.wakeupCall(self.sleepTime)
                    # check if we're at base (usually 3.9K), then set status -> ready
                    if self.at_base():
                        self.status = 'ready'

                elif self.status == 'ready':
                    yield util.wakeupCall(self.sleepTime)
                    # do we need to cool back down to 3.9K? (i.e. wait)
                    if not self.at_base():
                        self.status = 'cooling down'
                    # if scheduling is enabled, go to "waiting to mag up":
                    if self.state('schedulingActive'):
                        self.status = 'waiting to mag up'

                elif self.status == 'waiting to mag up':
                    yield util.wakeupCall(self.sleepTime)
                    # is scheduling still active?
                    if not self.state('schedulingActive'):
                        self.status = 'ready'
                    # do we need to cool back down to 3.9K? (i.e. wait)
                    elif not self.at_base():
                        self.status = 'cooling down'
                    # is it time to mag up?
                    elif time.time() > self.state('scheduledMagUpTime') and self.at_base():
                        self.status = 'magging up'

                elif self.status == 'ready to mag down':
                    yield util.wakeupCall(self.sleepTime)

                elif self.status == 'magging up':
                    print "Magging up..."
                    self.clear('magDownCompletedTime')
                    self.clear('magUpCompletedTime')
                    self.clear('scheduledMagDownTime')
                    # close heat switch if we've passed the 4K stage temperature
                    if not self.state('heatSwitched') and self.state('autoControl') \
                            and self.state('delayHeatSwitchClose'):
                        if self.ruox_status()[0] >= self.state('temperatures')[1]:
                            self.set_heat_switch(False)
                            self.state('heatSwitched', True)
                    (quenched, target_reached) = yield self.mag_step(True)  # True = mag step up
                    self.log("%s mag step! Quenched: %s -- Target Reached: %s" % (self.name, quenched, target_reached))
                    if quenched:
                        self.log("QUENCHED!")
                        self.status = 'cooling down'
                    elif target_reached:
                        print "got it"
                        self.status = 'waiting at field'
                        self.ps_max_current()
                        self.state('magUpCompletedTime', (time.time() / 60) * Unit('min'))
                        self.state('scheduledMagDownTime',
                                   (time.time() / 60) * Unit('min') + self.state('fieldWaitTime'))
                    else:
                        pass  # if at first we don't succeed, mag, mag again
                    yield util.wakeupCall(self.state('rampWaitTime')['s'])

                elif self.status == 'waiting at field':
                    yield util.wakeupCall(self.sleepTime)
                    # is it time to mag down?
                    if (time.time() / 60) * Unit('min') > self.state('scheduledMagDownTime'):
                        if not self.state('schedulingActive'):
                            self.status = 'ready to mag down'
                        else:
                            self.state('schedulingActive', False)
                            self.status = 'magging down'

                elif self.status == 'magging down':
                    (quenched, target_reached) = yield self.mag_step(False)
                    self.log("%s mag step! Quenched: %s -- Target Reached: %s" % (self.name, quenched, target_reached))
                    if quenched:
                        self.log("QUENCHED!")
                        self.status = 'cooling down'
                    elif target_reached:
                        self.status = 'ready'
                        self.state('magDownCompletedTime', time.time())
                        self.ps_output_off()
                    yield util.wakeupCall(self.state('rampWaitTime')['s'])

                elif self.status == 'pid control':
                    # try to get to the setTemp state variable with a PID control loop
                    # save old t error
                    terrOld = self.state('PIDterr')
                    # set current t error
                    self.state('PIDterr', self.state('PIDsetTemp') - self.ruox_status()[0], False)
                    print "PIDint: ", self.state("PIDint")
                    print "PIDterr: ", self.state("PIDterr")
                    self.state('PIDint', self.state('PIDint') + self.state('PIDterr') * self.sleepTime, False)
                    if abs(self.state('PIDint')) > self.state('PIDintLimit'):
                        self.state('PIDint',
                                   self.state('PIDintLimit') * np.sign(self.state('PIDint') / self.state('PIDci')),
                                   False)
                    P = self.state('PIDterr') * self.state('PIDcp')
                    I = self.state('PIDci') * self.state('PIDint')
                    if self.state('PIDloopCount') > 0:
                        D = self.state('PIDcd') * (self.state('PIDterr') - terrOld) / (self.sleepTime)
                    else:
                        D = 0.0 * V
                    # target voltage
                    self.state('PIDout', self.state('magVoltage') + P + I + D, False)
                    if self.state('PIDout') < 0:
                        self.state('PIDout', 0, False)
                    self.log('PID: T: %.4f K, V: %.4f V, P: %.4f V, I: %.4f V, D: %.4f V, PID: %.4f V' % (
                                self.ruox_status()[0]['K'], 
                                self.state('PIDout')['V'], 
                                P['V'], I['V'], D['V'], 
                                (P + I + D)['V']))
                    self.state('PIDloopCount', self.state('PIDloopCount') + 1, False)
                    # now step to it
                    yield self.PIDstep(self.state('PIDout'))
                    yield util.wakeupCall(self.sleepTime)

                else:
                    yield util.wakeupCall(self.sleepTime)
                    # end of if (status)
            # end of try
            except KeyboardInterrupt:  # , SystemExit):
                self.state('alive', False)
            except Exception as e:
                print "Exception in cycle loop: %s" % e.__str__()
                self.log("Exception in cycle loop: %s" % e.__str__())
                self.log(traceback.print_exc())
                yield util.wakeupCall(self.sleepTime)
        # end of while loop
        self.state('alive', False)

    def ruox_status(self):
        """
        Reads voltage from Lakeshore, converts to resistance, converts to temperature
        :return: (temperature, resistance)
        :rtype: (float, float)
        """
        ls_temps = self.state('temperatures')
        ruox_voltage = self.state('voltages')[self.state('ruoxChannel') - 1]  # LS218 channels are indexed from 1
        ruox_resistance = ruox_voltage * self.state('lockinOhmsPerVolt')
        # check for over temperature
        if ls_temps[1] > self.state('ruoxTempCutoff'):
            return ls_temps[1], ruox_resistance
        if self.state('useRuoxInterpolation'):
            temp = self.state('ruoxInterpolation')(ruox_resistance['Ohm'])[()] * K
        elif ruox_resistance < self.state('resistanceCutoff'):
            # high temp (2 to 20 K)
            # noinspection PyUnusedLocal
            r, p = ruox_resistance['Ohm'], self.state('ruoxCoefsHigh')
            temp = eval(self.state('highTempRuoxCurve')) * K
        else:
            # low temp (0.05 to 2 K)
            # noinspection PyUnusedLocal
            r, p = ruox_resistance['Ohm'], self.state('ruoxCoefsLow')
            temp = eval(self.state('lowTempRuoxCurve')) * K
        return temp, ruox_resistance

    def at_base(self):
        temps = self.state('temperatures')
        return (temps[1] < self.state('cooldownLimit')) and (temps[2] < self.state('cooldownLimit'))

    def ps_max_current(self):
        """ sets the magnet current to the max current. """
        new_current = min(PS_MAX_CURRENT, self.state('maxCurrent'))
        if new_current < 0:
            new_current = PS_MAX_CURRENT
        magnet = self.peripheralsConnected['magnet']
        self.log("%s magnet current -> %s" % (self.name, new_current))
        magnet.server.current(new_current, context=magnet.ctxt)

    @inlineCallbacks
    def ps_output_off(self):
        """ Turns off the magnet power supply, basically. """
        ps = self.peripheralsConnected['magnet']
        p = ps.server.packet(context=ps.ctxt)
        p.voltage(0 * V)
        p.current(0 * A)
        yield p.send()
        self.log("magnet voltage, current -> 0")
        yield util.wakeupCall(0.5)
        yield ps.server.output_state(False, context=ps.ctxt)
        self.log("magnet output_state -> false")

    @inlineCallbacks
    def ps_output_on(self):
        """ Turns on the power supply. """
        ps = self.peripheralsConnected['magnet']
        p = ps.server.packet(context=ps.ctxt)
        new_current = min(PS_MAX_CURRENT, self.state('maxCurrent'))
        if new_current < 0:
            new_current = PS_MAX_CURRENT
        p.current(new_current)
        p.output_state(True)
        yield p.send()
        self.log("magnet current -> %s\nmagnet output state -> %s" % (new_current, True))

    @inlineCallbacks
    def mag_step(self, up):
        """ If up is True, mags up a step. If up is False, mags down a step. """
        # don't mag if we don't have all the peripherals we need!
        if self.state('missingCriticalPeripheral'):
            print "Missing peripheral! Cannot mag! Check lakeshore and magnet!"
            self.log("Missing peripheral! Cannot mag! Check lakeshore and magnet!")
            yield util.wakeupCall(1.0)
            returnValue((False, False))
        # pull out the relevant values
        temps = self.state('temperatures')
        volts = self.state('voltages')
        current = self.state('magCurrent')
        voltage = self.state('magVoltage')
        # check for quench, reaching of mag target, and whether magnet voltage is within limits
        quenched = temps[1] > self.state('quenchLimit') and current > 0.5 * A
        if up:
            target_reached = self.state('targetCurrent') - current < 1 * mA
        else:
            target_reached = current < 10 * mA
        within_limits = abs(volts[6]) < self.state('voltageLimit') and abs(volts[7]) < self.state('voltageLimit')
        if (not quenched) and (not target_reached) and within_limits:
            if up:
                new_voltage = voltage + self.state('voltageStepUp')
            else:
                new_voltage = voltage - self.state('voltageStepDown')
            self.log("%s magnet voltage -> %s" % (self.name, new_voltage))
            ps = self.peripheralsConnected['magnet']
            yield ps.server.voltage(new_voltage, context=ps.ctxt)
        else:
            pass
        returnValue((quenched, target_reached))

    @inlineCallbacks
    def PIDstep(self, setV):
        """
        step the magnet to a voltage target.
        Note that this will repeatedly make small steps in the manner of a mag step.
        """
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
                verr = setV - self.state('magVoltage')
                if abs(verr) > max(self.state('voltageStepUp'), self.state('voltageStepDown')):
                    vnew = self.state('magVoltage') + max(self.state('voltageStepUp'),
                                                          self.state('voltageStepDown')) * np.sign(verr)
                    yield mag.server.voltage(vnew, context=self.ctxt)
                else:
                    doneStepping = True
                dt = time.time() - startTime
                if dt > self.state('PIDstepTimeout')['s']:
                    doneStepping = True
            yield util.wakeupCall(self.state('rampWaitTime')['s'])


    @inlineCallbacks
    def set_heat_switch(self, open_switch):
        """ open the heat switch (when open_switch=True), or close it (when open_switch=False) """
        if 'heatswitch' not in self.peripheralsConnected.keys():
            self.log('cannot open heat switch--server not connected!')
            return
        if open_switch:
            hs = self.peripheralsConnected['heatswitch']
            yield hs.server.open(context=hs.ctxt)
            self.log("open heat switch")
        else:
            hs = self.peripheralsConnected['heatswitch']
            yield hs.server.close(context=hs.ctxt)
            self.log("close heat switch")

    def set_compressor(self, start):
        """ if start==true, start compressor. if start==false, stop compressor """
        if start:
            cp = self.peripheralsConnected['compressor']
            cp.server.start(context=cp.ctxt)
            self.log("start compressor")
        else:
            cp = self.peripheralsConnected['compressor']
            cp.server.stop(context=cp.ctxt)
            self.log("stop compressor")

    #########################
    # DATA OUTPUT FUNCTIONS #
    #########################

    # getter/setter for state variables
    def state(self, var, new_value=None, log=True, no_new=False):
        """
        get/set a state variable.
        :param var: name of the state variable
        :param new_value: new value (optional)
        :param log: whether to log this change (default=True)
        :param no_new: if true, then don't create new one, only update existing (default=False)
        :return: Value
        """
        if no_new and new_value is not None and var not in self.stateVars:
            print "WARNING: not setting previously undefined state variable %s to %s" % (str(var), str(new_value))
            return None
        if new_value is not None:
            old_value = self.stateVars.get(var, None)
            self.stateVars[var] = new_value
            if log:
                self.log('Set %s to %s' % (var, str(new_value)))
            # if we changed the field wait time, we may need to change scheduled mag down time
            if var == 'fieldWaitTime' and self.state('magUpCompletedTime') > 1:
                self.state('scheduledMagDownTime', self.state('magUpCompletedTime') + new_value * 60.0)
            elif var == 'schedulingActive' and new_value:
                self.state('autoControl', True)
            elif var == 'tempRecordDelay':
                # update the deferred delayed call
                e = self.state('tempDelayedCall')
                if e:
                    try:
                        diff = new_value - old_value
                        e.reset(e.getTime() - time.time() + diff['s'])  # reset the counter
                    except twisted.internet.error.AlreadyCalled, twisted.internet.error.AlreadyCancelled:
                        pass
        return self.stateVars[var]

    # clear a state variable
    def clear(self, var):
        #del self.stateVars[var]
        self.stateVars[var] = None

    ###################################
    # TEMPERATURE RECORDING FUNCTIONS #
    ###################################

    # overall plan here:
    # once the temp dips below 250 K, take data every 10 min;
    # in critical periods, do it every 10 s.
    # a "critical period" would be triggered when you start magging up or on user command
    # it would end when the heat switch closes, when temp > (some value), after X hours, or on user command

    # noinspection PyAttributeOutsideInit
    def record_temp(self):
        """
        writes to the data vault.
        independent variable: time
        dependent variables: 50 K temperature (lakeshore 1), 4 K temperature (lakeshore 2), magnet temp (lakeshore 3),
            ruox voltage (lakeshore 4), ruox temp (converted--keep calibration as well?), and power supply V and I
        """
        try:
            dv = self.cxn.data_vault
            ds_name = self.state('tempDatasetName')
            if ds_name and ds_name[18:20] != time.strftime('%m'):  # start new dataset if it's a new day
                self.state('tempDatasetName', None)
            if not self.state('tempDatasetName'):
                # we need to create a new dataset
                dv.cd(self.state('datavaultPath'), True, context=self.ctxt)
                self.indeps = [('time', 's')]
                self.deps = [
                    ('temperature', 'ch1: 50K', 'K'),
                    ('temperature', 'ch2: 4K', 'K'),
                    ('temperature', 'ch3: mag', 'K'),
                    ('voltage', 'ch4: ruox', 'V'),
                    ('resistance', 'ruox', 'Ohm'),
                    ('temperature', 'ruox', 'K'),
                    ('voltage', 'magnet', 'V'),
                    ('current', 'magnet', 'A'),
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
                dv.new(name, self.indeps, self.deps, context=self.ctxt)
                print "Started new recording dataset: %s" % name
                self.state('tempDatasetName', name)
            # assemble the info
            temps = self.state('temperatures')
            volts = self.state('voltages')
            ruox = self.ruox_status()
            i, v = (self.state('magCurrent'), self.state('magVoltage'))
            t = int(time.time()) * s
            cp_temps = self.state('compressorTemperatures')
            cp_press = self.state('compressorPressures')
            cp_cpu = self.state('compressorCPUTemperature')
            cp_motor = self.state('compressorMotorCurrent')
            # save the data
            values = [t, temps[0], temps[1], temps[2], volts[3], ruox[1], ruox[0], v, i, temps[4]] \
                + list(cp_temps) + [cp_motor, cp_cpu] + list(cp_press) + [temps[3]] + list(temps[5:]) \
                + list(volts[0:3]) + list(volts[4:])
            floats = []
            for value, unit in zip(values, self.indeps + self.deps):
                floats.append(value[unit[-1]])
            dv.add(floats, context=self.ctxt)
            # log!
            #self.log("Temperature log recorded: %s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(t)))
        except Exception as e:
            print "Exception in data logging: %s" % e.__str__()
            self.log("Exception in data logging: %s" % e.__str__())

    @inlineCallbacks
    def recording_cycle(self):
        """
        this function should be called when the temperature recording starts, and will return when it stops.
        it will loop every either 10s or 10 min and then call record temp.
        this also checks each time to see if we should continue recording.
        """
        while self.state('recordTemp'):
            # make the record
            self.record_temp()

            # check if we should stop recording
            if self.state('autoRecord') and self.should_stop_recording():
                self.stop_recording()
                break

            d = defer.Deferred()  # we use a blank deferred, so nothing will actually happen when we finish
            e = reactor.callLater(self.state('tempRecordDelay')['s'], d.callback, None)
            self.state('tempDelayedCall', e, False)
            # and now, we wait.
            yield d
            # note that we can interrupt the waiting by messing with the e object (saved in a state variable)

    def start_recording(self):
        self.state('recordTemp', True)
        reactor.callLater(0.1, self.recording_cycle)
        #self.tempCycle()

    def stop_recording(self):
        self.state('recordTemp', False)
        self.state('tempDatasetName', None)
        e = self.state('tempDelayedCall')
        if e:
            try:
                e.reset(0)  # reset the counter
            except twisted.internet.error.AlreadyCalled:
                pass

    def should_start_recording(self):
        """
        determines whether we should start recording.
        """
        temps = self.state('temperatures')
        if len(self.peripheralsConnected.items()) == 0:
            return False
        return (self.state('recordingTemp') > temps[0] > 0*K) \
            or (self.state('recordingTemp') > temps[0] > 0*K) \
            or self.state('compressorStatus')

    def should_stop_recording(self):
        """
        determines whether to stop recording.
        conditions: temp > 250K, --???
        """
        return not self.should_start_recording()


    #################################
    # PERIPHERAL HANDLING FUNCTIONS #
    #################################

    # noinspection PyAttributeOutsideInit
    @inlineCallbacks
    def refreshPeripherals(self, refreshGPIB=False):
        while self._refreshPeripheralLock:
            yield util.wakeupCall(0.25)
        self._refreshPeripheralLock = True
        self.allPeripherals = yield self.findPeripherals(refresh_gpib=refreshGPIB)
        print self.allPeripherals
        self.peripheralOrphans = {}
        self.peripheralsConnected = {}
        for peripheralName, idTuple in self.allPeripherals.items():
            yield self.attemptPeripheral((peripheralName, idTuple))
        self._refreshPeripheralLock = False

    @inlineCallbacks
    def findPeripherals(self, refresh_gpib=False):
        """Finds peripheral device definitions for a given ADR (from the registry)
        OUTPUT
            peripheral_dict - dictionary {peripheralName:(serverName,identifier)..}
        """

        reg = self.cxn.registry
        ctxt = reg.context()
        yield reg.cd(CONFIG_PATH + [self.name], context=ctxt)
        dirs, keys = yield reg.dir(context=ctxt)
        p = reg.packet(context=ctxt)
        for peripheral in keys:
            p.get(peripheral, key=peripheral)
        ans = yield p.send(context=ctxt)
        peripheral_dict = {}
        for peripheral in keys:  # all key names in this directory
            peripheral_dict[peripheral] = ans[peripheral]
        # pomalley 2013-01-25 -- refresh the GPIB bus when we do this
        # pomalley 2013-02-21 -- do it conditionally
        if refresh_gpib:
            node_list = [v[1] for v in peripheral_dict.itervalues()]
            deferred_list = []
            for node in set(node_list):
                for serverName, server in self.cxn.servers.iteritems():
                    if serverName.lower().startswith(node.lower()) and 'gpib' in serverName.lower():
                        deferred_list.append(server.refresh_devices())
                        print "refreshing %s" % serverName
            for d in deferred_list:
                yield d
        returnValue(peripheral_dict)

    @inlineCallbacks
    def attemptOrphans(self):
        for peripheralName, idTuple in self.peripheralOrphans.items():
            yield self.attemptPeripheral((peripheralName, idTuple))

    @inlineCallbacks
    def attemptPeripheral(self, peripheralTuple):
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
            print 'Server ' + serverName + ' does not exist.',
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
            print 'Server ' + serverName + ' does not have device ' + peripheralID
            self._orphanPeripheral(peripheralTuple)

    @inlineCallbacks
    def _connectPeripheral(self, server, peripheralTuple):
        peripheralName = peripheralTuple[0]
        ID = peripheralTuple[1][1]
        #Make the actual connection to the peripheral device!
        self.peripheralsConnected[peripheralName] = Peripheral(peripheralName, server, ID, self.ctxt)
        yield self.peripheralsConnected[peripheralName].connect()
        print "connected to %s for %s" % (ID, peripheralName)

    def _orphanPeripheral(self, peripheralTuple):
        peripheralName = peripheralTuple[0]
        idTuple = peripheralTuple[1]
        if peripheralName not in self.peripheralOrphans:
            self.peripheralOrphans[peripheralName] = idTuple

    #####################
    # LOGGING FUNCTIONS #
    #####################

    # noinspection PyAttributeOutsideInit
    def log(self, data):
        # write to log file
        with open(self.state('logfile'), 'a') as f:
            f.write('%s -- %s\n' % (time.strftime("%Y-%m-%d %H:%M:%S"), data))
        # append to log variable
        print 'stardate %s: %s' % (time.strftime("%Y-%m-%d %H:%M:%S"), data)
        self.logData.append((time.strftime("%Y-%m-%d %H:%M:%S"), data))
        # check to truncate log to last X entries
        if len(self.logData) > self.state('loglimit'):
            self.logData = self.logData[-self.state('loglimit'):]

    def get_log(self):
        return self.logData

    def get_entire_log(self):
        with open(self.state('logfile')) as f:
            log_string = f.read()
        return log_string


# (end of ADRWrapper)

# #####################################
# ######### ADR SERVER CLASS ##########
# #####################################


class ADRServer(DeviceServer):
    name = 'ADR Server'
    deviceName = 'ADR'
    deviceWrapper = ADRWrapper

    # def initServer(self):
    #	return DeviceServer.initServer(self)

    #def stopServer(self):
    #	return DeviceServer.stopServer(self)

    @inlineCallbacks
    def findDevices(self):
        """
        Finds all ADR configurations in the registry at CONFIG_PATH and returns a list of
        (ADR_name,(),peripheralDictionary).
        INPUTS - none
        OUTPUT - List of (ADRName,(connectionObject,context),peripheralDict) tuples.
        """
        device_list = []
        reg = self.client.registry
        yield reg.cd(CONFIG_PATH)
        resp = yield reg.dir()
        adr_names = resp[0].aslist
        for name in adr_names:
            if 'defaults' not in name:
                # all required nodes must be present to create this device
                yield reg.cd(name)
                devices = yield reg.dir()
                devices = devices[1].aslist
                missing_nodes = []
                for dev in devices:
                    node = yield reg.get(dev)
                    node = node[1].split(' ')[0]
                    if "node_" + node.lower() not in self.client.servers:
                        missing_nodes.append(node)
                if not missing_nodes:
                    device_list.append((name, (self.client,)))
                else:
                    print "device %s missing nodes: %s" % (name, str(list(set(missing_nodes))))
                yield reg.cd(1)

        returnValue(device_list)

    @setting(211, 'refresh gpib')
    def refresh_gpib(self, c):
        """Refreshes all relevant GPIB buses and then looks for peripherals."""
        dev = self.selectedDevice(c)
        yield dev.refreshPeripherals(refreshGPIB=True)

    @setting(21, 'refresh peripherals', returns=[''])
    def refresh_peripherals(self, c):
        """Refreshes peripheral connections for the currently selected ADR"""

        dev = self.selectedDevice(c)
        yield dev.refreshPeripherals()

    @setting(22, 'list all peripherals', returns='*?')
    def list_all_peripherals(self, c):
        dev = self.selectedDevice(c)
        peripheral_list = []
        for peripheral, idTuple in dev.allPeripherals.items():
            peripheral_list.append((peripheral, idTuple))
        return peripheral_list

    @setting(23, 'list connected peripherals', returns='*?')
    def list_connected_peripherals(self, c):
        dev = self.selectedDevice(c)
        connected = []
        for name, peripheral in dev.peripheralsConnected.items():
            connected.append((peripheral.name, peripheral.ID))
        return connected

    @setting(24, 'list orphans', returns='*?')
    def list_orphans(self, c):
        dev = self.selectedDevice(c)
        orphans = []
        for peripheral, idTuple in dev.peripheralOrphans.items():
            orphans.append((peripheral, idTuple))
        return orphans

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

    @setting(42, 'Magnet Status', returns=['(v[A] v[V])'])
    def magnet_status(self, c):
        """ Returns the voltage and current from the magnet power supply. """
        dev = self.selectedDevice(c)
        return dev.state('magCurrent'), dev.state('magVoltage')

    @setting(43, 'Compressor Status', returns=['b'])
    def compressor_status(self, c):
        """ Returns True if the compressor is running, false otherwise. """
        dev = self.selectedDevice(c)
        return dev.state('compressorStatus')

    @setting(44, 'Ruox Status', returns=['(v[K] v[Ohm])'])
    def ruox_status(self, c):
        """ Returns the temperature and resistance measured at the cold stage. """
        dev = self.selectedDevice(c)
        return dev.ruox_status()

    @setting(45, 'Set Compressor', value='b')
    def set_compressor(self, c, value):
        """ True starts the compressor, False stops it. """
        dev = self.selectedDevice(c)
        dev.set_compressor(value)

    @setting(46, 'Set Heat Switch', value='b')
    def set_heat_switch(self, c, value):
        """ 
        True opens the heat switch, False closes it.
        There is no confirmation! Don't mess up.
        """
        dev = self.selectedDevice(c)
        dev.set_heat_switch(value)

    @setting(50, 'List State Variables', returns=['*s'])
    def list_state_variables(self, c):
        """ Returns a list of all the state variables for this ADR. """
        dev = self.selectedDevice(c)
        return dev.stateVars.keys()

    @setting(51, 'Set State', variable='s', value='?')
    def set_state(self, c, variable, value):
        """ Sets the given state variable to the given value. """
        dev = self.selectedDevice(c)
        dev.state(variable, value)

    @setting(52, 'Get State', variable='s', returns=["?"])
    def get_state(self, c, variable):
        """ Gets the value of the given state variable. """
        dev = self.selectedDevice(c)
        return dev.state(variable)

    @setting(53, 'Status', returns=['s'])
    def status(self, c):
        """ Returns the status (e.g. "cooling down", "waiting to mag up", etc.) """
        dev = self.selectedDevice(c)
        return dev.status

    @setting(54, 'List Statuses', returns=['*s'])
    def list_statuses(self, c):
        """ Returns a list of all allowed statuses. """
        dev = self.selectedDevice(c)
        return dev.possibleStatuses

    @setting(55, 'Change Status', value='s')
    def change_status(self, c, value):
        """ Changes the status of the ADR server. """
        dev = self.selectedDevice(c)
        dev.status = value

    @setting(56, "Get Log", returns=['*(ss)'])
    def get_log(self, c):
        """ Gets this ADR's log. """
        dev = self.selectedDevice(c)
        return dev.get_log()

    @setting(57, "Write Log", value='s')
    def write_log(self, c, value):
        """ Writes a single entry to the log. """
        dev = self.selectedDevice(c)
        dev.log(value)

    @setting(58, "Revert to Defaults")
    def revert_to_defaults(self, c):
        """ Reverts the state variables to the defaults in the registry. """
        dev = self.selectedDevice(c)
        dev.load_defaults_from_registry()

    @setting(59, "Get Entire Log")
    def get_entire_log(self, c):
        """ Gets the entire log. It is very large and you probably don't want to do this. """
        dev = self.selectedDevice(c)
        return dev.get_entire_log()

    # the 60's settings are for controlling the temp recording
    @setting(60, "Start Recording")
    def start_recording(self, c):
        """ Start recording temp. """
        dev = self.selectedDevice(c)
        dev.state('autoRecord', False)
        dev.start_recording()

    @setting(61, "Stop Recording")
    def stop_recording(self, c):
        """ Stop recording temp. """
        self.selectedDevice(c).stop_recording()

    @setting(62, "Is Recording")
    def is_recording(self, c):
        """ Returns whether recording or not. """
        dev = self.selectedDevice(c)
        return dev.state('recordTemp')

    @setting(63, "Mag Step", up='b')
    def mag_step(self, c, up):
        """ mag step """
        dev = self.selectedDevice(c)
        dev.mag_step(up)


__server__ = ADRServer()

if __name__ == '__main__':
    from labrad import util

    util.runServer(__server__)
