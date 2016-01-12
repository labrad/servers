# Copyright (C) 2011 Jim Wenner
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
name = Agilent Infiniium Oscilloscope
version = 0.2
description = Talks to the Agilent DSO91304A 13GHz oscilloscope

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""



from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as U
from struct import unpack, calcsize

import string
import struct
import time
import numpy, re

COUPLINGS = ['AC', 'DC', 'GND']
TRIG_CHANNELS = ['AUX','CH1','CH2','CH3','CH4','LINE']
VERT_DIVISIONS = 8.0
HORZ_DIVISIONS = 10.0
SCALES = []

class AgilentDSO91304AServer(GPIBManagedServer):
    name = 'Agilent Infiniium Oscilloscope'
    deviceName = ['Agilent Technologies DSO91304A', 'KEYSIGHT TECHNOLOGIES DSO90804A']
        
    @setting(11, returns=[])
    def reset(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('*RST')
        # TODO wait for reset to complete

    @setting(12, returns=[])
    def clear_buffers(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('*CLS')

    #Channel settings
    @setting(100, channel = 'i', returns = '(vvvvsvss)')
    def channel_infoNONEXISTANT(self, c, channel):
        """channel(int channel)
        Get information on one of the scope channels.

        OUTPUT
        Tuple of (probeAtten, termination, scale, position, coupling, bwLimit, invert, units)
        """
        raise Exception('Not yet implemented')
        #NOTES
        #The scope's response to 'CH<x>?' is a string of format
        #'1.0E1;1.0E1;2.5E1;0.0E0;DC;OFF;OFF;"V"'
        #These strings represent respectively,
        #probeAttenuation;termination;vertScale;vertPosition;coupling;bandwidthLimit;invert;vertUnit

        dev = self.selectedDevice(c)
        resp = yield dev.query('CH%d?' %channel)
        bwLimit, coupling, deskew, offset, invert, position, scale, termination, probeCal, probeAtten, resistance, unit, textID, textSN, extAtten, extUnits, textLabel, xPos, yPos = resp.split(';')

        #Convert strings to numerical data when appropriate
        probeAtten = T.Value(float(probeAtten),'')
        termination = T.Value(float(termination),'')
        scale = T.Value(float(scale),'')
        position = T.Value(float(position),'')
        coupling = coupling
        bwLimit = T.Value(float(bwLimit),'')
        invert = invert
        unit = unit[1:-1] #Get's rid of an extra set of quotation marks

        returnValue((probeAtten,termination,scale,position,coupling,bwLimit,invert,unit))

    @setting(111, channel = 'i', coupling = 's', returns=['s'])
    def couplingNONEXISTANT(self, c, channel, coupling = None):
        """Get or set the coupling of a specified channel
        Coupling can be "AC", "DC", or "GND"
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CH%d:COUP?' %channel)
        else:
            coupling = coupling.upper()
            if coupling not in COUPLINGS:
                raise Exception('Coupling must be "AC", "DC", or "GND"')
            else:
                yield dev.write(('CH%d:COUP '+coupling) %channel)
                resp = yield dev.query('CH%d:COUP?' %channel)
        returnValue(resp)

    @setting(112, channel = 'i', scale = 'v', returns = ['v'])
    def scale(self, c, channel, scale = None):
        """Get or set the vertical scale of a channel in voltage per division.
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('CHAN%d:SCAL?' %channel)
        else:
            scale = format(scale,'E')
            yield dev.write(('CHAN%d:SCAL '+scale) %channel)
            resp = yield dev.query('CHAN%d:SCAL?' %channel)
        scale = float(resp)
        returnValue(scale)

    @setting(113, channel = 'i', factor = 'i', returns = ['s'])
    def probeNONEXISTANT(self, c, channel, factor = None):
        """Get or set the probe attenuation factor.
        """
        raise Exception('Not yet implemented')
        probeFactors = [1,10,20,50,100,500,1000]
        dev = self.selectedDevice(c)
        chString = 'CH%d:' %channel
        if factor is None:
            resp = yield dev.query(chString+'PRO?')
        elif factor in probeFactors:
            yield dev.write(chString+'PRO %d' %factor)
            resp = yield dev.query(chString+'PRO?')
        else:
            raise Exception('Probe attenuation factor not in '+str(probeFactors))
        returnValue(resp)

    @setting(114, channel = 'i', state = '?', returns = 's')
    def channelOnOff(self, c, channel, state = None):
        """Turn on or off a scope channel display.
        State must be in [0,1,'ON','OFF'].
        Channel must be int.
        If state is not specified, will return state of channel.
        """
        dev = self.selectedDevice(c)
        if state is None:
            resp = yield dev.query('CHAN%d:DISP?' %channel)
        else:
            if isinstance(state, int):
                state = str(state)
            elif isinstance(state, str):
                state = state.upper()
            else:
                raise Exception('state must be int or string')
            if state not in ['0','1','ON','OFF']:
                raise Exception('state must be 0, 1, "ON", or "OFF"')
            yield dev.write(('CHAN%d:DISP '+state) %channel)
            resp = yield dev.query('CHAN%d:DISP?' %channel)
        returnValue(resp)

    @setting(115, channel = 'i', invert = 'i', returns = ['i'])
    def invertNONEXISTANT(self, c, channel, invert = None):
        """Get or set the inversion status of a channel
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if invert is None:
            resp = yield dev.query('CH%d:INV?' %channel)
        else:
            yield dev.write(('CH%d:INV %d') %(channel,invert))
            resp = yield dev.query('CH%d:INV?' %channel)
        invert = int(resp)
        returnValue(invert)

    @setting(117, channel = 'i', position = 'v', returns = ['v'])
    def position(self, c, channel, position = None):
        """Get or set the voltage at the center of the screen
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('CHAN%d:OFFS?' %channel)
        else:
            yield dev.write(('CHAN%d:OFFS %f') %(channel,position))
            resp = yield dev.query('CHAN%d:OFFS?' %channel)
        position = float(resp)
        returnValue(position)
        
    @setting(118, mode =  ['s','i','b'], returns = ['s'])
    def averagemode(self, c, mode = None):
        """Get or set acquisition mode
        """
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.query('ACQ:AVER?')
        else:
            if mode is not None:
                if isinstance(mode, str):
                    mode = {'ON':1,'OFF':0}[mode]
                elif isinstance(mode, bool):
                    mode = int(mode)
                elif isinstance(mode, int):
                    pass       
            yield dev.write('ACQ:AVER '+str(mode))
            resp = yield dev.query('ACQ:AVER?')
        returnValue(resp) 
        
    @setting(119, navg = 'i', returns = ['i'])
    def numavg(self, c, navg = None):
        """Get or set number of averages
        """
        dev = self.selectedDevice(c)
        if navg is None:
            resp = yield dev.query('ACQ:COUN?')
        else:    
            yield dev.write('ACQ:COUN %d' %navg)
            resp = yield dev.query('ACQ:COUN?')
        navg_out = int(resp)
        returnValue(navg_out)         

    @setting(131, channel = 'i', level = 'v', returns = 'v{level}')
    def trigger_at(self, c, channel, level = None):
        """Get or set the trigger source and the trigger voltage for edge mode triggering.
        Channel must be one of 0 (AUX), 1, 2, 3, 4.
        """
        dev = self.selectedDevice(c)
        if channel not in [0,1,2,3,4]:
            raise Exception('Select valid trigger channel')
            
        if channel==0:
            channel = 'AUX'
        else:
            channel = 'CHAN%d' %channel
            
        if level is None:
            resp = yield dev.query('TRIG:LEV? %s' %channel)
        else:
            yield dev.write('TRIG:EDGE:SOUR %s' %channel) #set channel up for edge triggering  
            yield dev.write('TRIG:LEV %s,%f' %(channel,level)) #set trigger level
            resp = yield dev.query('TRIG:LEV? %s' %channel)
        level = float(resp)
        returnValue(level)

    @setting(132, slope = 's', returns = ['s'])
    def trigger_mode(self, c, slope = None):
        """Change trigger mode. Use 'EDGE' for edge triggering.
        Must be one of 'COMM','DEL','EDGE','GLIT','PATT','PWID','RUNT','SEQ',',SHOL','STAT','TIM','TRAN','TV',',WIND','SBUS1','SBUS2','SBUS3','SBUS4'.
        """
        dev = self.selectedDevice(c)
        if slope is None:
            resp = yield dev.query('TRIG:MODE?')
        else:
            slope = slope.upper()
            if slope not in ['COMM','DEL','EDGE','GLIT','PATT','PWID','RUNT','SEQ',',SHOL','STAT','TIM','TRAN','TV',',WIND','SBUS1','SBUS2','SBUS3','SBUS4']:
                raise Exception('Slope must be valid type.')
            else:
                yield dev.write('TRIG:MODE '+slope)
                resp = yield dev.query('TRIG:MODE?')
        returnValue(resp)

    @setting(133, slope = 's', returns = ['s'])
    def trigger_edge_slope(self, c, slope = None):
        """Change trigger edge slope.
        Must be 'POS,' 'NEG', or 'EITH'er
        """
        dev = self.selectedDevice(c)
        if slope is None:
            resp = yield dev.query('TRIG:EDGE:SLOP?')
        else:
            slope = slope.upper()
            if slope not in ['POS','NEG','EITH']:
                raise Exception('Slope must be "RISE" or "FALL"')
            else:
                yield dev.write('TRIG:EDGE:SLOP '+slope)
                resp = yield dev.query('TRIG:EDGE:SLOP?')
        returnValue(resp)

    @setting(134, mode = 's', returns = ['s'])
    def trigger_sweep(self, c, mode = None):
        """Get or set the trigger mode
        Must be "AUTO", "TRIG" (normal), or "SING" (single)
        """
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.query('TRIG:SWE?')
        else:
            mode = mode.upper()
            if mode not in ['AUTO','TRIG','SING']:
                raise Exception('Mode must be "AUTO", "TRIG", or "SING".')
            else:
                yield dev.write('TRIG:SWE '+mode)
                resp = yield dev.query('TRIG:SWE?')
        returnValue(resp)

    @setting(150, side = 's', returns = ['s'])
    def horiz_refpoint(self, c, side = None):
        """Get or set the reference point for the horizontal position. Must be 'LEFT', 'CENT'er, or 'RIGH't.
        """
        dev = self.selectedDevice(c)
        if side is None:
            resp = yield dev.query('TIM:REF?')
        else:
            side = side.upper()
            if side not in ['LEFT','CENT','RIGH']:
                raise Exception('Mode must be "LEFT", "CENT", or "RIGH".')
            else:
                yield dev.write('TIM:REF '+side)
                resp = yield dev.query('TIM:REF?')
        returnValue(resp)

    @setting(151, position = 'v', returns = ['v'])
    def horiz_position(self, c, position = None):
        """Get or set the horizontal trigger position (wrt value from horiz_refpoint) in seconds.
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('TIM:POS?')
        else:
            yield dev.write(('TIM:POS %f') %position)
            resp = yield dev.query('TIM:POS?')
        position = float(resp)
        returnValue(position)

    @setting(152, scale = 'v', returns = ['v'])
    def horiz_scale(self, c, scale = None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('TIM:SCAL?')
        else:
            scale = format(scale,'E')
            yield dev.write('TIM:SCAL '+scale)
            resp = yield dev.query('TIM:SCAL?')
        scale = float(resp)
        returnValue(scale)
    
    #Data acquisition settings
    @setting(201, channel = 'i', start = 'i', stop = 'i', returns='*v[ns] {time axis} *v[mV] {scope trace}')
    def get_trace(self, c, channel, start=1, stop=10000, points=100000):
        """Get a trace from the scope.
        OUTPUT - (array voltage in volts, array time in seconds)
        """
        #raise Exception('Doesnt work yet. Please fix lines defining traceVolts and time.')
##        DATA ENCODINGS
##        RIB - signed, MSB first
##        RPB - unsigned, MSB first
##        SRI - signed, LSB first
##        SRP - unsigned, LSB first
        wordLength = 2 #Hardcoding to set data tranfser word length to 2 bytes
        
        dev = self.selectedDevice(c)
        yield dev.write('WAV:SOUR CHAN%d' %channel)
        #Read data MSB first
        yield dev.write('WAV:BYT MSBF')
        #Set 2 bytes per point
        yield dev.write('WAV:FORM BYTE')
        yield dev.write('ACQUIRE:POINTS %s'%points)
        #Starting and stopping point
        #Transfer waveform preamble
        # Display the waveform settings from preamble:
        wav_form_dict = {
        0 : "ASCii",
        1 : "BYTE",
        2 : "WORD",
        3 : "LONG",
        4 : "LONGLONG",
        }
        acq_type_dict = {
        1 : "RAW",
        2 : "AVERage",
        3 : "VHIStogram",
        4 : "HHIStogram",
        6 : "INTerpolate",
        10 : "PDETect",
        }
        acq_mode_dict = {
        0 : "RTIMe",
        1 : "ETIMe",
        3 : "PDETect",
        }
        coupling_dict = {
        0 : "AC",
        1 : "DC",
        2 : "DCFIFTY",
        3 : "LFREJECT",
        }
        units_dict = {
        0 : "UNKNOWN",
        1 : "VOLT",
        2 : "SECOND",
        3 : "CONSTANT",
        4 : "AMP",
        5 : "DECIBEL",
        }
        #Transfer waveform preamble
        preamble_string = yield dev.query('WAV:PRE?',timeout=10.0*U.s)
        (
        wav_form, acq_type, wfmpts, avgcnt, x_increment, x_origin,
        x_reference, y_increment, y_origin, y_reference, coupling,
        x_display_range, x_display_origin, y_display_range,
        y_display_origin, date, time, frame_model, acq_mode,
        completion, x_units, y_units, max_bw_limit, min_bw_limit
        ) = string.split(preamble_string, ",")
        
        # Get numeric values for later calculations.
        x_increment = yield dev.query(':WAVeform:XINCrement?')
        x_origin = yield dev.query(':WAVeform:XORigin?')
        y_increment = yield dev.query(':WAVeform:YINCrement?')
        y_origin = yield dev.query(':WAVeform:YORigin?')
        # Get the waveform data.
        dev.write(':WAVeform:STReaming OFF')
        #Transfer waveform data
        sData = yield dev.query(':WAVeform:DATA?')
        #Parse binary
        sBlock = sData
        # First character should be "#".
        pound = sBlock[0:1]
        if pound != "#":
            print "PROBLEM: Invalid binary block format, pound char is '%s'." % pound
            print "Exited because of problem."
            sys.exit(1)
        # Second character is number of following digits for length value.
        digits = sBlock[1:2]
        # Get the data out of the block and return it.
        sData = sBlock[int(digits) + 2:]

        # Unpack signed byte data.
        values = struct.unpack("%db" % len(sData), sData)

        time = []
        traceVolts = []

        x_increment = float(x_increment)
        x_origin = float(x_origin)
        y_increment = float(y_increment)
        y_origin = float(y_origin)

        for i in xrange(0, len(values) - 1):
            time_val = x_origin + (i * x_increment)
            voltage = (values[i] * y_increment) + y_origin
            time.append(time_val)
            traceVolts.append(voltage)
        
        returnValue((time*U.ns*1e9, traceVolts*U.V))
        
        

        
        
# def _parsePreamble(preamble):
    # preambleVals = preamble.split(',')
    # '''
    # preambleKeys = [('byteFormat',True),
                    # ('dataType',False),
                    # ('numPoints',True),
                    # ('count',False),
                    # ('xStep',True),
                    # ('xFirst',True),
                    # ('xRef',False),
                    # ('yStep',True),
                    # ('yOrigin',True),
                    # ('yRef',False),
                    # ('coupling',False),
                    # ('xRange',True),
                    # ('xLeftDisplay',True),
                    # ('yRange',True),
                    # ('yCenterDisplay',True),
                    # ('date',False),
                    # ('time',False),
                    # ('model',False),
                    # ('acquisitionMode',False),
                    # ('percentTimeBucketsComplete',False),
                    # ('xUnits',True),
                    # ('yUnits',True),
                    # ('maxBW',False),
                    # ('minBW',False)]
    # '''
    # preambleKeys = [('byteFormat',True),
                # ('dataType',True),
                # ('numPoints',True),
                # ('count',True),
                # ('xStep',True),
                # ('xFirst',True),
                # ('xRef',True),
                # ('yStep',True),
                # ('yOrigin',True),
                # ('yRef',True),
                # ('coupling',True),
                # ('xRange',True),
                # ('xLeftDisplay',True),
                # ('yRange',True),
                # ('yCenterDisplay',True),
                # ('date',True),
                # ('time',True),
                # ('model',True),
                # ('acquisitionMode',True),
                # ('percentTimeBucketsComplete',True),
                # ('xUnits',True),
                # ('yUnits',True),
                # ('maxBW',True),
                # ('minBW',True)]
    # preambleDict = {}
    # for key,val in zip(preambleKeys,preambleVals):
        # print 'key:  ', key,'  val:  ', val
        # if key[1]:
            # preambleDict[key[0]] = val
    # def unitType(num):
        # if num=='1':
            # return 'V'
        # elif num=='2':
            # return 'ns'
        # else:
            # raise Exception('Units not time or voltage')
    # preambleDict['xUnit'] = unitType(preambleDict['xUnits'])
    # preambleDict['yUnit'] = unitType(preambleDict['yUnits'])
    # return (preambleDict)

# def _parseBinaryData(data, wordLength):
    # """Parse binary data packed as string of RIBinary
    # """
    # formatChars = {'1':'b','2':'h', '4':'f'}
    # formatChar = formatChars[str(wordLength)]

    # Get rid of header crap
    # unpack binary data
    # if wordLength == 1:
        # lenHeader = int(data[1])
        # dat = data[(2+lenHeader):]
        # dat = numpy.array(unpack(formatChar*(len(dat)/wordLength),dat))
    # elif wordLength == 2:
        # lenHeader = int(data[1])
        # dat = data[(2+lenHeader):]
        # dat = dat[-calcsize('>' + formatChar*(len(dat)/wordLength)):]
        # dat = numpy.array(unpack('>' + formatChar*(len(dat)/wordLength),dat))
    # elif wordLength == 4:
        # lenHeader = int(data[1])
        # dat = data[(2+lenHeader):]
        # dat = dat[-calcsize('>' + formatChar*(len(dat)/wordLength)):]
        # dat = numpy.array(unpack('>' + formatChar*(len(dat)/wordLength),dat))      
    # return dat

__server__ = AgilentDSO91304AServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
