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
name = Agilent DSO91304A Oscilloscope
version = 0.1
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
from labrad.types import Value
from struct import unpack, calcsize

import numpy, re

COUPLINGS = ['AC', 'DC', 'GND']
TRIG_CHANNELS = ['AUX','CH1','CH2','CH3','CH4','LINE']
VERT_DIVISIONS = 10.0
HORZ_DIVISIONS = 10.0
SCALES = []

class AgilentDSO91304AWrapper(GPIBDeviceWrapper):
    pass

class AgilentDSO91304AServer(GPIBManagedServer):
    name = 'AGILENT 13GHZ DSO91304A OSCILLOSCOPE'
    deviceName = 'AGILENT TECHNOLOGIES DSO91304A'
    deviceWrapper = AgilentDSO91304AWrapper
        
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

    @setting(114, channel = '?', state = '?', returns = '')
    def channelOnOff(self, c, channel, state):
        """Turn on or off a scope channel display.
        State must be in [0,1,'ON','OFF'].
        Channel must be int or string.
        """
        dev = self.selectedDevice(c)
        if isinstance(state, str):
            state = state.upper()
        if state not in [0,1,'ON','OFF']:
            raise Exception('state must be 0, 1, "ON", or "OFF"')
        if isinstance(state, int):
            state = str(state)
        if isinstance(channel, str):
            channel = channel.upper()
        elif isinstance(channel, int):
            channel = 'CH%d' %channel
        else:
            raise Exception('channel must be int or string')
        yield dev.write(('CHAN%s:DISP '+state) %channel)

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

    @setting(131, slope = 's', returns = ['s'])
    def trigger_slopeNONEXISTANT(self, c, slope = None):
        """Turn on or off a scope channel display
        Must be 'RISE' or 'FALL'
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if slope is None:
            resp = yield dev.query('TRIG:A:EDGE:SLO?')
        else:
            slope = slope.upper()
            if slope not in ['RISE','FALL']:
                raise Exception('Slope must be "RISE" or "FALL"')
            else:
                yield dev.write('TRIG:A:EDGE:SLO '+slope)
                resp = yield dev.query('TRIG:A:EDGE:SLO?')
        returnValue(resp)

    @setting(132, level = 'v', returns = ['v'])
    def trigger_levelNONEXISTANT(self, c, level = None):
        """Get or set the vertical zero position of a channel in units of divisions
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if level is None:
            resp = yield dev.query('TRIG:A:LEV?')
        else:
            yield dev.write(('TRIG:A:LEV %f') %level)
            resp = yield dev.query('TRIG:A:LEV?')
        level = float(resp)
        returnValue(level)

    @setting(133, channel = '?', returns = ['s'])
    def trigger_channelNONEXISTANT(self, c, channel = None):
        """Get or set the trigger source
        Must be one of "AUX","LINE", 1, 2, 3, 4, "CH1", "CH2", "CH3", "CH4"
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if isinstance(channel, str):
            channel = channel.upper()
        if isinstance(channel, int):
            channel = 'CH%d' %channel
            
        if channel is None:
            resp = yield dev.query('TRIG:A:EDGE:SOU?')
        elif channel in TRIG_CHANNELS:
            yield dev.write('TRIG:A:EDGE:SOU '+channel)
            resp = yield dev.query('TRIG:A:EDGE:SOU?')
        else:
            raise Exception('Select valid trigger channel')
        returnValue(resp)

    @setting(134, mode = 's', returns = ['s'])
    def trigger_modeNONEXISTANT(self, c, mode = None):
        """Get or set the trigger mode
        Must be "AUTO" or "NORM"
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.query('TRIG:A:MOD?')
        else:
            mode = mode.upper()
            if mode not in ['AUTO','NORM']:
                raise Exception('Mode must be "AUTO" or "NORM".')
            else:
                yield dev.write('TRIG:A:MOD '+mode)
                resp = yield dev.query('TRIG:A:MOD?')
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
        position = float(resp)
        returnValue(position)

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
    def get_traceNONEXISTANT(self, c, channel, start=1, stop=10000):
        """Get a trace from the scope.
        OUTPUT - (array voltage in volts, array time in seconds)
        """
        raise Exception('Not yet implemented')
##        DATA ENCODINGS
##        RIB - signed, MSB first
##        RPB - unsigned, MSB first
##        SRI - signed, LSB first
##        SRP - unsigned, LSB first
        wordLength = 2 #Hardcoding to set data transer word length to 2 bytes
        recordLength = stop-start+1
        
        dev = self.selectedDevice(c)
        #DAT:SOU - set waveform source channel
        yield dev.write('DAT:SOU CH%d' %channel)

        #DAT:ENC - data format (binary/ascii)
        yield dev.write('DAT:ENC RIB')
        #Set number of bytes per point
        yield dev.write('DAT:WID %d' %wordLength)
        #Starting and stopping point
        yield dev.write('DAT:STAR %d' %start)
        yield dev.write('DAT:STOP %d' %stop)
        #Transfer waveform preamble
        preamble = yield dev.query('WFMP?')
        position = yield dev.query('CH%d:POSITION?' %channel) # in units of divisions
        #Transfer waveform data
        binary = yield dev.query('CURV?')
        #Parse waveform preamble
        voltsPerDiv, secPerDiv, voltUnits, timeUnits = _parsePreamble(preamble)
        voltUnitScaler = Value(1, voltUnits)['mV'] # converts the units out of the scope to mV
        timeUnitScaler = Value(1, timeUnits)['ns']
        #Parse binary
        trace = _parseBinaryData(binary,wordLength = wordLength)
        #Convert from binary to volts
        traceVolts = (trace * (1/32768.0) * VERT_DIVISIONS/2 * voltsPerDiv - float(position) * voltsPerDiv) * voltUnitScaler
        time = numpy.linspace(0, HORZ_DIVISIONS * secPerDiv * timeUnitScaler,len(traceVolts))#recordLength)

        returnValue((time, traceVolts))

def _parsePreamble(preamble):
    ###TODO: parse the rest of the preamble and return the results as a useful dictionary
    preamble = preamble.split(';')
    vertInfo = preamble[5].split(',')
    
    def parseString(string): # use 'regular expressions' to parse the string
        number = re.sub(r'.*?([\d\.]+).*', r'\1', string)
        units = re.sub(r'.*?([a-zA-z]+)/.*', r'\1', string)
        return float(number), units
    
    voltsPerDiv, voltUnits = parseString(vertInfo[2])
    if voltUnits == 'VV':
        voltUnits ='W'
    if voltUnits == 'mVV':
        voltUnits = 'W'
    if voltUnits == 'uVV':
        voltUnits = 'W'
    if voltUnits == 'nVV':
        voltUnits = 'W'
    secPerDiv, timeUnits = parseString(vertInfo[3])
    return (voltsPerDiv, secPerDiv, voltUnits, timeUnits)

def _parseBinaryData(data, wordLength):
    """Parse binary data packed as string of RIBinary
    """
    formatChars = {'1':'b','2':'h', '4':'f'}
    formatChar = formatChars[str(wordLength)]

    #Get rid of header crap
    #unpack binary data
    if wordLength == 1:
        dat = numpy.array(unpack(formatChar*(len(dat)/wordLength),dat))
    elif wordLength == 2:
        header = data[0:6]
        dat = data[6:]
        dat = dat[-calcsize('>' + formatChar*(len(dat)/wordLength)):]
        dat = numpy.array(unpack('>' + formatChar*(len(dat)/wordLength),dat))
    elif wordLength == 4:
        header = data[0:6]
        dat = data[6:]
        dat = dat[-calcsize('>' + formatChar*(len(dat)/wordLength)):]
        dat = numpy.array(unpack('>' + formatChar*(len(dat)/wordLength),dat))      
    return dat

__server__ = AgilentDSO91304AServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
