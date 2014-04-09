# Copyright (C) 2007  Matthew Neeley
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

# Version 2.1	pomalley	7/23/2010	Added reading of calibrations from
# LabRAD registry.
# Version 2.2	pomalley	8/17/2010	Fixed some issues with above, added
# reading of Read Order from registry.
# Version 2.3   pomalley    4/01/2010   Added r and auto_sensitivity settings
# Version 2.4   Daniel Sank 2013/10/23  Support multiple devices on a single
#                                       node(gpib bus).
#                                       Added named_temperatures
# Version 2.5   Jim Wenner  2014/03/24  No longer needing to scan consecutive
#                                       channels
# Version 2.5.1 Jim Wenner  2014/04/09  If using interpolation, resistances no
#                                       longer must be monotonically increasing
#
# How to set your Lakeshore 370's Resistance vs. Temperature Curve:
# Previously, conversion of a resistance to a temperature happened with a hard
# coded function. Now that we have two DRs, and thus (at least) two different
# kinds of Ruox thermometers, a single hard coded function will not be
# sufficient. Information for the calibration curves will be stored in the
# registry; there can be different curves for each Lakeshore device, as well as
# different curves for each channel on a given device. The registry entries for
# a given device are stored in the following path:
# >> Servers >> Lakeshore 370 >> [node name] >> [GPIB address]
# where [node name] is something like "Vince" or "DR"
# (note that the node name is actually taken from the first word of the device
# wrapper's self.name) A given calibration consists of three keys:
#   Calibration Type: must either be "Interpolation" or "Function"
# 	For an interpolation, there must be two more keys:
#		"Resistances", an array of resistance values, and
#		"Temperatures", an array of corresponding temperatures.
#		In this case, the server will do a log-log interpolation of the given
#       data to convert a resistance to a temperature.
#	For a function, there must be one more key:
#		"Function", which is a string of a Python expression for converting a
#       res to a temp, and "Inverse", which is also a Python expression, but
#       inverted (for converting a temp to a res). In the Function, the
#       resistance variable is r; in the Inverse, the temperature variable is
#       t. In both cases, math functions are imported in the namespace	math
#       (e.g. use math.log(r) to take the log). The server will run the
#       Function code to convert a resistance to a temperature. For example,
#       the function that is used for Jules' resistors is:
#       '((math.log(r) - 6.02) / 1.76) ** (-1/.345)'
#		The Inverse code is used for temperature regulation. (Note that for
#       interpolation calibrations the server can simply reverse the arguments
#       of the interpolation to convert a temp to a res).
#
# The best way to understand these is by example. Look in >> Servers >>
# Lakeshore 370 >> Jules for an example of a function, and >> Servers >>
# Lakeshore 370 >> Vince >> <gpib addr> for an interpolation example. Finally,
# if you need to have different calibrations for different resistors on the
# same device, this can easily be accomplished by creating another folder
# called "Channel X" where X is one of 1 - N, and then put the appropriate keys
# in that folder. That calibration will be used for that channel, and the
# calibration for the device will only be used if there is no calibration for a
# given channel. In this way, you can have an interpolation for channel 1, a
# different interpolation for channel 2, and a function for the device, which
# would be used for channels 3, 4, and 5, for example. For an example of this,
# see >> Servers >> Lakeshore 370 >> Vince >> <gpib addr>.

# Also note that the read order for a given device now can be stored in the
# registry as well. If not, it defaults to [1, 2, 1, 3, 1, 4, 1, 5]

"""
### BEGIN NODE INFO
[info]
name = Lakeshore RuOx
version = 2.5.1
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from datetime import datetime
import math

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper

import numpy as np

READ_ORDER = [1, 2, 1, 3, 1, 4, 1, 5]
#N_CHANNELS = 5
SETTLE_TIME = 8
DEFAULT, FUNCTION, INTERPOLATION = range(3)

def res2temp(r):
    try:
        return ((math.log(r) - 6.02) / 1.76) ** (-1/.345)
    except Exception:
        return 0.0

def temp2res(t):
    try:
        return math.exp(1.76*(t**(-0.345)) + 6.02)
    except Exception:
        return 0.0

class RuOxWrapper(GPIBDeviceWrapper):
    
    @inlineCallbacks
    def initialize(self):
        """Set up initial state for this wrapper"""
        self.alive = False
        self.onlyChannel = 0
        print "Initializing %s" % self.name
        yield self.loadDeviceInformation()
        # also we should set the box settings here
        yield self.write('RDGRNG 0,0,04,15,1,0')
        self.alive = True
        self.readLoop().addErrback(log.err)	
    
    @inlineCallbacks
    def loadDeviceInformation(self):
        """Get a wrapper around this device's registry data"""
        path = self.getRegistryPath()
        #Load calibration data
        yield self.reloadCalibrations(path)
        yield self.reloadChannelNames(path)
    
    def getRegistryPath(self):
        """Get a registry path suitable for registry.cd
        
        Warning - the registry is controlled by the same program as the manager
        which runs in Windoze. This means that paths are case insensitive.
        """
        path = ['', 'Servers', 'Lakeshore 370']
        gpibServerName, addr = self.name.split(' - ')
        nodeName = gpibServerName.split(' ')[0].lower()
        path.extend([nodeName, addr])
        return path
    
    @inlineCallbacks
    def reloadChannelNames(self, path):
        reg = self.gpib._cxn.registry
        p = reg.packet()
        p.cd(path)
        p.get('channelNames', key='channels')
        ans = yield p.send()
        self.channelNames = ans['channels']
    
    @inlineCallbacks
    def loadSingleCalibration(self, reg, path):
        """Load a single calibration
        
        reg = registry object
        path = directory where registry keys are. For example:
        ["", "Servers", "Lakeshore 370", "GPIB1::12", "Channel 1"]
        
        Returns a list: [regType, parameters...]
        
        For regType == DEFAULT there are no parameters and len(returnValue) = 1
        For regType == FUNCTION, the returnValue [1] is a string of python code
        to be eval'd in a place where r (float) is a resistance, in ohms, and
        returnValue[2] is the inverse of the function, where t (float) is a
        temp, in kelvin for regType == INTERPOLATION, then returnValue[1] is a
        list of resistances for interpolation, and returnValue[2] is a list of
        temperatures.
        """
        try:
            p = reg.packet()
            p.cd(path)
            p.get("Calibration Type", key="type")
            ans = yield p.send()
            if ans.type.upper() == "INTERPOLATION":
                p = reg.packet()
                p.cd(path)
                p.get("Resistances", key="res")
                p.get("Temperatures", key="temp")
                ans = yield p.send()
                calOrder = np.argsort(ans.res)
                returnValue([INTERPOLATION, np.array(ans.res)[calOrder], np.array(ans.temp)[calOrder]])
            elif ans.type.upper() == "FUNCTION":
                p = reg.packet()
                p.cd(path)
                p.get("Function", key="fun")
                p.get("Inverse", key="inv")
                ans = yield p.send()
                returnValue([FUNCTION, ans.fun, ans.inv])
            else:
                returnValue([DEFAULT])
        except Exception, e:
            print e
            returnValue([DEFAULT])
    
    def printCalibration(self, channel):
        str = ''
        try:
            if self.calibrations[channel][0] == INTERPOLATION:
                str = "INTERPOLATION --  Resistances: %s -- Temperatures: %s"%\
                (self.calibrations[channel][1], self.calibrations[channel][2])
            elif self.calibrations[channel][0] == FUNCTION:
                str = "FUNCTION: %s -- Inverse: %s" %\
                (self.calibrations[channel][1], self.calibrations[channel][2])
            elif self.calibrations[channel][0] == DEFAULT:
                str = "DEFAULT"
            else:
                raise Exception('Invalid calibration for channel %s: "%s"' %\
                                   (channel, str))
        except Exception, e:
            str += e.__str__()
            
        return str
    
    @inlineCallbacks
    def reloadCalibrations(self, dir):
        """Load read order and resistance->temperature function from registry
        
        There are actually multiple functions--one for each channel, and a
        device default in case any of the channels' are missing
        self.calibrations[0] = device default calibration,
        self.calibrations[1-N] for channels 1-N. See docstring for
        loadSingleCalibration
        """
        self.calibrations = []
        self.readOrder = []
        reg = self.gpib._cxn.registry
        # Get the read order from the registry
        try:
            p = reg.packet()
            p.cd(dir)
            p.get("Read Order", key="ro")
            ans = yield p.send()
            self.readOrder = ans["ro"]
        except Exception:
            self.readOrder = READ_ORDER
        
        # initialize the readings variable.
        # len(set(x)) gets the number of unique elements in x
        self.readings = {}
        for channel in self.readOrder:
            self.readings[channel] = (0, datetime.now())
        
        # now start with the calibrations
        # first get the default one
        calib = yield self.loadSingleCalibration(reg, dir)
        self.calibrations.append(calib)
        if self.calibrations[0][0] == DEFAULT:
            print "WARNING: %s -- no calibration found for device default. Using server default calibration." % (self.addr)
        elif self.calibrations[0][0] == INTERPOLATION:
            print "%s -- found INTERPOLATION calibration for device default." % (self.addr)
        elif self.calibrations[0][0] == FUNCTION:
            print "%s -- found FUNCTION calibration for device default." % (self.addr)
        else:
            raise Exception("Calibration loader messed up. This shouldn't have happened.")
        # now do all channels
        for i in range(max(self.readOrder)):
            calib = yield self.loadSingleCalibration(reg, dir + ['Channel %d' % (i+1)])
            self.calibrations.append(calib)
            if self.calibrations[i+1][0] == DEFAULT:
                print "WARNING: %s -- no calibration found for channel %d. Using device default calibration." % (self.addr, i+1)
            elif self.calibrations[i+1][0] == INTERPOLATION:
                print "%s -- found INTERPOLATION calibration for channel %d." % (self.addr, i+1)
            elif self.calibrations[i+1][0] == FUNCTION:
                print "%s -- found FUNCTION calibration for channel %d." % (self.addr, i+1)
            else:
                raise Exception("Calibration loader messed up. This shouldn't have happened.")
    
    def shutdown(self):
        self.alive = False
    
    @inlineCallbacks
    def selectChannel(self, channel):
        yield self.write('SCAN %d,0' % channel)
    
    @inlineCallbacks
    def getHeaterOutput(self):
        ans = yield self.query('HTR?')
        returnValue(float(ans))
    
    @inlineCallbacks
    def setHeaterRange(self, value):
        if value is None:
            yield self.write('HTRRNG 0')
            returnValue(None)
        else:
            value = float(value)
            val = 8
            for limit in [31.6, 10, 3.16, 1, 0.316, 0.1, 0.0316]:
                if value <= limit:
                    val -= 1
            yield self.write('HTRRNG %d' % val)
            returnValue([0.0316, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0][val-1])
    
    @inlineCallbacks
    def controlTemperature(self, channel, resistance, loadresistor):
        yield self.write('HTRRNG 0')
        yield self.write('CSET %d,0,2,1,1,8,%f' % (channel, loadresistor))
        yield self.write('SETP %f' % resistance)
    
    @inlineCallbacks
    def setPID(self, P, I, D):
        yield self.write('PID %f, %f, %f' % (P, I, D))
    
    @inlineCallbacks
    def readLoop(self, idx=0):
        while self.alive:
            # read only one specific channel
            if self.onlyChannel > 0:
                chan = self.onlyChannel
                yield util.wakeupCall(SETTLE_TIME)
                r = yield self.query('RDGR? %d' % chan)
                self.readings[chan] = float(r), datetime.now()
            # scan over channels
            else:
                if len(self.readOrder) > 0:
                    chan = self.readOrder[idx]
                else:
                    yield util.wakeupCall(SETTLE_TIME)
                    continue
                yield self.selectChannel(chan)
                yield util.wakeupCall(SETTLE_TIME)
                r = yield self.query('RDGR? %d' % chan)
                self.readings[chan] = float(r), datetime.now()
                idx = (idx + 1) % len(self.readOrder)
    
    def getSingleTemp(self, channel, calIndex=-1):
        """Get a single temperature for a given channel
        
        Use that channel's calibration, or if it's default, the device
        calibration (and if that's zero, the default function) the first
        argument is the channel the second argument is the channel to use for
        the calibration, where 0 means use device default calibration if we
        don't find a calibration on the given channel, we try again with 0 if
        that doesn't work, we use the old-fashioned res2temp.
        """
        if calIndex == -1:
            calIndex = channel
        try:
            print("lakeshore370: Computing temperature for channel %d"%channel)
            print("Resistance is %f"%self.readings[channel][0])
            if self.calibrations[calIndex][0] == INTERPOLATION:
                # log-log interpolation
                return (np.exp(np.interp(np.log(self.readings[channel][0]),
                              np.log(np.array(self.calibrations[calIndex][1])),
                              np.log(np.array(self.calibrations[calIndex][2]))
                              )))
            elif self.calibrations[calIndex][0] == FUNCTION:
                # hack alert--using eval is bad:
                # (1) This depends on the function string being good python
                #     code.
                # (2) It also depends on it having "r" as the variable for 
                #     resistance, in ohms.
                # (3) very unsafe if anyone ever hacks the registry. of course,
                #     then we have bigger problems
                r = self.readings[channel][0]
                return eval(self.calibrations[calIndex][1])
            elif self.calibrations[calIndex][0] == DEFAULT:
                if calIndex > 0:
                    # use calibration 0--the device calibration
                    return self.getSingleTemp(channel, 0) 
                else:
                    #If there is no calibration at all use res2temp
                    return res2temp(self.readings[channel][0])
        except Exception, e:
            print e
            return 0.0
    
    def getTemperatures(self):
        # we now do this channel by channel. oh yeah.
        result = []
        for channel in sorted(self.readings.keys()):
            result.append((self.getSingleTemp(channel), self.readings[channel][1]))
        return result
    
    def getNamedTemperatures(self):
        # we now do this channel by channel. oh yeah.
        result = []
        for channel in sorted(self.readings.keys()):
            result.append((self.channelNames[channel-1],(self.getSingleTemp(channel), self.readings[channel][1])))
        return result
    
    def getResistances(self):
        result = []
        for channel in sorted(self.readings.keys()):
            result.append(self.readings[channel])
        return result
    
    def getNamedResistances(self):
        result = []
        for channel in sorted(self.readings.keys()):
            result.append((self.channelNames[channel-1],self.readings[channel]))
        return result
    
    def singleTempToRes (self, temp, channel, calIndex=-1):
        """Get the resistance that corresponds to a temperature
        
        You need to provide the channel because different channels can have
        different calibrations this function is essentially the inverse of
        getSingleTemp.
        """
        if calIndex == -1:
            calIndex = channel
        try:
            if self.calibrations[calIndex][0] == INTERPOLATION:
                # do the log-log interpolation in reverse
                return (np.exp(np.interp(np.log(temp),
                                            np.log(np.array(self.calibrations[calIndex][2][::-1])),
                                            np.log(np.array(self.calibrations[calIndex][1][::-1]))
                                            )))
            elif self.calibrations[calIndex][0] == FUNCTION:
                # same as getSingleTemp, but use inverse instead of function
                t = temp
                return eval(self.calibrations[calIndex][2])
            elif eslf.calibrations[calIndex][0] == DEFAULT:
                if calIndex > 0:
                    return self.singleTempToRes(temp, channel, 0) # use calibration 0
                else:
                    return temp2res(temp) # if no calibration for the device either, use old-fashioned temp2res
        except Exception, e:
            print "Exception converting temp to res: %s" % e.__str__()
            return 0.0
            
class LakeshoreRuOxServer(GPIBManagedServer):
    name = 'Lakeshore RuOx'
    deviceName = 'LSCI MODEL370'
    deviceWrapper = RuOxWrapper
    
    @setting(111, "r", returns='v[Ohm]')
    def r(self, c):
        ''' return the resistance '''
        r = self.resistances(c)
        return r[0][0]
    
    @setting(112, 'auto_sensitivity')
    def auto_sensitivity(self, c):
        pass
    
    @setting(10, 'Temperatures', returns='*(v[K], t)')
    def temperatures(self, c):
        """Read channel temperatures.

        Returns a ValueList of the channel temperatures in Kelvin.
        """
        dev = self.selectedDevice(c)
        return dev.getTemperatures()
    
    @setting(11, 'Named Temperatures', returns='*(s, (v[K], t))')
    def named_temperatures(self, c):
        dev = self.selectedDevice(c)
        return dev.getNamedTemperatures()
    
    @setting(12, 'Resistances', returns='*(v[Ohm], t)')
    def resistances(self, c):
        """Read channel resistances.

        Returns a ValueList of the channel resistances in Ohms.
        """
        dev = self.selectedDevice(c)
        return dev.getResistances()
    
    @setting(13, 'Named Resistances', returns='*(s, (v[Ohm], t))')
    def named_resistances(self, c):
        dev = self.selectedDevice(c)
        return dev.getNamedResistances()
    
    @setting(20, 'Select channel', channel='w', returns='w')
    def selectchannel(self, c, channel):
        """Select channel to be read. If argument is 0,
        scan over channels.

        Returns selected channel.
        """
        dev = self.selectedDevice(c)
        dev.onlyChannel = channel
        if channel > 0:
            dev.selectChannel(channel)
        return channel
    
    @setting(21, "Single Temperature", channel='w', returns='(v[K], t)')
    def single_temperature(self, c, channel):
        """Read a single temperature. Argument must be a valid channel.

        Returns temperature in Kelvin, and time of measurement.
        """
        dev = self.selectedDevice(c)
        return (dev.getSingleTemp(channel), dev.readings[channel-1][1])
    
    @setting(22, 'Reload Calibrations')
    def reload(self, c):
        """Reloads the parameters that are stored in the registry.
        
        This includes:
        * Calibration curves/interpolation tables for all channels and the
          device default
        * Channel read order
        Call this after you change something in the registry and want to reload
        it.
        """
        dev = self.selectedDevice(c)
        dev.reloadCalibrations()
    
    @setting(23, 'Print Settings', returns='s')
    def print_settings(self, c):
        """Prints the settings loaded from the registry for this device."""
        dev = self.selectedDevice(c)
        string = ''
        string += "Read order: %s  \n  " % dev.readOrder.__str__()
        string += "Device default calibration: %s  \n  " %\
            dev.printCalibration(0)
        for i in range(1, 6):
            string += "Channel %s calibration: %s  \n  " %\
                (i, dev.printCalibration(i))
        return string
    
    @setting(50, 'Regulate Temperature', channel='w', temperature='v[K]',
                 loadresistor='v[Ohm]', returns='v[Ohm]: Target resistance')
    def regulate(self, c, channel, temperature, loadresistor=30000):
        """Initializes temperature regulation

        NOTE:
        Use "Heater Range" to turn on heater and start regulation."""
        dev = self.selectedDevice(c)
        if channel not in range(1,17):
            raise Exception('Channel needs to be between 1 and 16')
        #res = temp2res(float(temperature))
        # we now do it intelligently
        res = dev.singleTempToRes(float(temperature), channel)
        if res == 0.0:
            raise Exception('Invalid temperature')
        loadresistor = float(loadresistor)
        if (loadresistor < 1) or (loadresistor > 100000):
            msg = 'Load resistor value must be between 1 Ohm and 100kOhm'
            raise Exception(msg)
        dev.onlyChannel = channel
        dev.selectChannel(channel)
        yield dev.controlTemperature(channel, res, loadresistor)
        returnValue(res)
    
    @setting(52, 'PID', P='v', I='v[s]', D='v[s]')
    def setPID(self, c, P, I, D=0):
        P = float(P)
        if (P < 0.001) or (P > 1000):
            raise Exception('P value must be between 0.001 and 1000')
        I = float(I)
        if (I < 0) or (I > 10000):
            raise Exception('I value must be between 0s and 10000s')
        D = float(D)
        if (D < 0) or (D > 2500):
            raise Exception('D value must be between 0s and 2500s')
        dev = self.selectedDevice(c)
        yield dev.setPID(P, I, D)
    
    @setting(55, 'Heater Range', limit=['v[mA]: Set to this current', ' : Turn heater off'], returns=['v[mA]', ''])
    def heaterrange(self, c, limit=None):
        """Sets the Heater Range"""
        dev = self.selectedDevice(c)
        ans = yield dev.setHeaterRange(limit)
        returnValue(ans)
    
    @setting(56, 'Heater Output', returns='v[%]')
    def heateroutput(self, c):
        """Queries the current Heater Output"""
        dev = self.selectedDevice(c)
        ans = yield dev.getHeaterOutput()
        returnValue(ans)
    
__server__ = LakeshoreRuOxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
