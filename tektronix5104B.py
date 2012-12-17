# Copyright (C) 2011 Jim Wenner, 2012 Rami Barends
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
#
# 2012: added support for average mode
"""
### BEGIN NODE INFO
[info]
name = Tektronix TDS 5104B Oscilloscope
version = 0.3
description = Talks to the Tektronix 5104B oscilloscope

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""



from labrad import util
from labrad.units import Unit,Value
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.types import Value
from struct import unpack

import numpy, re

BANDWIDTHS = ['TWE', 'ONE', 'FUL']
COUPLINGS = ['AC', 'DC', 'GND']
TRIG_CHANNELS = ['AUX','CH1','CH2','CH3','CH4','LINE']
VERT_DIVISIONS = 10.0
HORZ_DIVISIONS = 10.0
VERT_SCALES_MV = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]

class Tektronix5104BWrapper(GPIBDeviceWrapper):
    
    @inlineCallbacks
    def reset(self):
        yield self.write('*RST')

    @inlineCallbacks
    def clearBuffers(self):
        yield self.write('*CLS')
    
    @inlineCallbacks
    def channelBandwidth(self, ch, bw=None):
        if bw is not None:
            yield self.write('CH%d:BAN %s' %(ch,bw))
        resp = yield self.query('CH%d:BAN?' %ch)
        returnValue(resp)
        
    @inlineCallbacks
    def coupling(self, ch, coup=None):
        if coup is not None:
            yield self.write('CH%d:COUP %s' %(ch, coup))
        resultCoup = yield self.query('CH%d:COUP?' %ch)
        returnValue(resultCoup)
        
    @inlineCallbacks
    def invert(self, ch, invert=None):
        if invert is not None:
            yield self.write('CH%d:INV %d' %(ch, invert))
        resp = yield self.query('CH%d:INV?' %ch)
        returnValue(resp)        
        
    @inlineCallbacks
    def measureType(self, slot, measType=None):
        if measType is not None:
            yield self.write('MEASU:MEAS%d:TYP %s' %(slot, measType))
        measType = yield self.query('MEASU:MEAS%d:TYP?' %slot)
        returnValue(measType)

    @inlineCallbacks
    def measureValue(self, slot):
        result = yield self.query('MEASU:MEAS%d:UNI?;VAL?' %slot)
        u, v = result.split(';')
        v = float(v)
        u = Unit(u[1:-1])
        returnValue(v*u)
        
    @inlineCallbacks
    def measureSource(self, slot, source=None):
        if source is not None:
            yield self.write('MEASU:MEAS%d:SOURCE[1] %s' %(slot,source))
        resp = yield self.query('MEASU:MEAS%d:SOURCE[1]?' %slot)
        returnValue(resp)
        
    @inlineCallbacks
    def scale(self, ch, sc=None):
        if sc is not None:
            scaleStr_V = format(sc['V'], 'E')        
            yield self.write('CH%d:SCA %s' %(ch, scaleStr_V))
        resp = yield self.query('CH%d:SCA?' %ch)
        returnValue(Value(float(resp),'V'))
    
    @inlineCallbacks
    def horizScale(self, sc=None):
        if sc is not None:
            scStr_sec = format(sc['s'], 'E')
            yield self.write('HOR:SCA %s' %scStr_sec)
        resp = yield self.query('HOR:SCA?')
        returnValue(Value(float(resp), 's'))
    
    @inlineCallbacks
    def mathDefinition(self, slot, expression):
        if expression is not None:
            yield self.write('MATH%d:DEF %s' %(slot, expression))
        resp = yield self.query('MATH%d:DEF?' %slot)
        returnValue(resp)
            
class Tektronix5104BServer(GPIBManagedServer):
    name = 'TEKTRONIX 5104B OSCILLOSCOPE'
    deviceName = 'TEKTRONIX TDS5104B'
    deviceWrapper = Tektronix5104BWrapper
    
    @setting(11, returns=[])
    def reset(self, c):
        dev = self.selectedDevice(c)
        yield dev.reset()
        # TODO wait for reset to complete

    @setting(12, returns=[])
    def clear_buffers(self, c):
        dev = self.selectedDevice(c)
        yield dev.clearBuffers()

    #CHANNEL SETTINGS
    
    @setting(100, channel = 'i', returns = '(vvvvsvss)')
    def channel_info(self, c, channel):
        """channel(int channel)
        Get information on one of the scope channels.

        OUTPUT
        Tuple of (probeAtten, termination, scale, position, coupling, bwLimit, invert, units)

        NOTES
        The scope's response to 'CH<x>?' is a string of format
        '1.0E1;1.0E1;2.5E1;0.0E0;DC;OFF;OFF;"V"'
        These strings represent respectively,
        probeAttenuation;termination;vertScale;vertPosition;coupling;bandwidthLimit;invert;vertUnit
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('CH%d?' %channel)
        bwLimit, coupling, deskew, offset, invert, position, scale, termination, probeCal, probeAtten, resistance, unit, textID, textSN, extAtten, extUnits, textLabel, xPos, yPos = resp.split(';')

        #Convert strings to numerical data when appropriate
        probeAtten = Value(float(probeAtten),'')
        termination = Value(float(termination),'')
        scale = Value(float(scale),'')
        position = Value(float(position),'')
        coupling = coupling
        bwLimit = Value(float(bwLimit),'')
        invert = invert
        unit = unit[1:-1] #Get's rid of an extra set of quotation marks

        returnValue((probeAtten,termination,scale,position,coupling,bwLimit,invert,unit))

    @setting(101, channel = 'i', bw = 's', returns = 'v[Hz]')
    def bandwidth(self, c, channel, bw = None):
        """Get or set the bandwidth of a specified channel
        
        Bandwidths can be specified as strings. Allowed strings are \n
        'TWE' : 20MHz \n        
        'ONE' : 150MHz \n
        'FIV' : 500MHz (*This one doesn't work so I removed it from the allowed list*) \n
        'FUL': Remove bandwidth limit \n
        
        RETURNS \n
        Value - bandwidth of this channel
        
        COMMENTS \n
        When setting a bandwidth, no checking is done to ensure that the
        requested value is actually selected in the device, although the
        current value is queried and returned
        
        """
        if (bw is not None) and (bw not in BANDWIDTHS):
            raise Exception('Bandwidth must be one of the following: %s' %BANDWIDTHS)
        dev = self.selectedDevice(c)
        resp = yield dev.channelBandwidth(channel, bw)
        bw = Value(float(resp),'Hz')
        returnValue(bw)
    
    @setting(102, ch = 'i', coup = 's', returns='s')
    def coupling(self, c, ch, coup = None):
        """Get or set the coupling of a specified channel
        Coupling can be "AC", "DC", or "GND"
        """
        dev = self.selectedDevice(c)
        if (coup is not None) and (coup not in COUPLINGS):
            raise Exception('coupling must be in %s' %COUPLINGS)
        resp = yield dev.coupling(ch, coup)       
        returnValue(resp)

    @setting(103, ch = 'i', invert = ['s','i','b'], returns = 'i')
    def invert(self, c, ch, invert = None):
        """Get or set the inversion status of a channel
        """
        dev = self.selectedDevice(c)
        if invert is not None:
            if isinstance(invert, str):
                invert = {'ON':1,'OFF':0}[invert]
            elif isinstance(invert, bool):
                invert = int(invert)
            elif isinstance(invert, int):
                pass
        resp = yield dev.invert(ch, invert)
        returnValue(int(resp))
    
    #VERTICAL

    @setting(200, ch = 'i', sc = 'v[mV]', returns = 'v[mV]')
    def scale(self, c, ch, sc = None):
        """Get or set the vertical scale of a channel
        """
        dev = self.selectedDevice(c)
        result = yield dev.scale(ch, sc)
        returnValue(result)
    
    #HORIZONTAL
    
    @setting(300, scale = 'v[s]', returns = 'v[s]')
    def horiz_scale(self, c, scale = None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        resp = yield dev.horizScale(scale)
        returnValue(resp)
        
    #MEASUREMENTS
    
    @setting(400, slot='i', measType = 's', returns='s')
    def measure_type(self, c, slot, measType):
        """Set the type of measurement for one of the measurement slots
        
        Available slots are 1 through 8
        
        For a complete list of possibly measurements see the programmer's
        manual.
        
        """
        if not (slot>=1 and slot<=8):
            raise Exception('Measurement slot must be in range 1 to 8')
        dev = self.selectedDevice(c)
        result = yield dev.measureType(slot, measType)
        returnValue(result)
    
    @setting(401, slot='i', returns='v')
    def measure_value(self, c, slot):
        dev = self.selectedDevice(c)
        result = yield dev.measureValue(slot)
        returnValue(result)
    
    @setting(402, slot='i', source='s', returns='')
    def measure_source(self, c, slot, source=None):
        raise Exception('this does not work for some weird reason')
        dev = self.selectedDevice(c)
        resp = yield dev.measureSource(slot, source)
        returnValue(resp)
        
    #MATH
    
    @setting(500, slot='i', expression='s', returns='s')
    def math_definition(self, c, slot, expression=None):
        dev = self.selectedDevice(c)
        resp = yield dev.mathDefinition(slot, expression)
        returnValue(resp)
    
    #CHECKED BY DAN TO HERE
    
    @setting(113, channel = 'i', factor = 'i', returns = ['s'])
    def probe(self, c, channel, factor = None):
        """Get or set the probe attenuation factor.
        """
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

    @setting(114, channel = 'i', state = '?', returns = '')
    def channelOnOff(self, c, channel, state):
        """Turn on or off a scope channel display
        """
        dev = self.selectedDevice(c)
        if isinstance(state, str):
            state = state.upper()
        if state not in [0,1,'ON','OFF']:
            raise Exception('state must be 0, 1, "ON", or "OFF"')
        if isinstance(state, int):
            state = str(state)
        yield dev.write(('SEL:CH%d '+state) %channel)

        
        
    @setting(116, channel = 'i', termination = 'v', returns = ['v'])
    def termination(self, c, channel, termination = None):
        """Get or set the a channels termination
        Can be 50 or 1E+6
        """
        dev = self.selectedDevice(c)
        if termination is None:
            resp = yield dev.query('CH%d:TER?' %channel)
        elif termination in [50,1e6]:
            yield dev.write(('CH%d:TER %f') %(channel,termination))
            resp = yield dev.query('CH%d:SCA?' %channel)
        else:
            raise Exception('Termination must be 50 or 1E+6')
        termination = float(resp)
        returnValue(termination)

    @setting(117, channel = 'i', position = 'v', returns = ['v'])
    def position(self, c, channel, position = None):
        """Get or set the vertical zero position of a channel in units of divisions
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('CH%d:POS?' %channel)
        else:
            yield dev.write(('CH%d:POS %f') %(channel,position))
            resp = yield dev.query('CH%d:POS?' %channel)
        position = float(resp)
        returnValue(position)

    @setting(118, mode = 's', returns = ['s'])
    def acquisition_mode(self, c, mode = None):
        """Get or set acquisition mode
        """
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.query('ACQ:MOD?')
        else:
            if mode not in ['SAM','PEAK','HIR','AVE','ENV']:
                raise Exception('state must be "SAM","PEAK","HIR","AVE","ENV"')        
            yield dev.write('ACQ:MOD '+mode)
            resp = yield dev.query('ACQ:MOD?')
        returnValue(resp)        
        
    @setting(119, navg = 'i', returns = ['i'])
    def numavg(self, c, navg = None):
        """Get or set number of averages
        """
        dev = self.selectedDevice(c)
        if navg is None:
            resp = yield dev.query('ACQ:NUMAV?')
        else:    
            yield dev.write('ACQ:NUMAV %d' %navg)
            resp = yield dev.query('ACQ:NUMAV?')
        navg_out = int(resp)
        returnValue(navg_out)          
        
    @setting(131, slope = 's', returns = ['s'])
    def trigger_slope(self, c, slope = None):
        """Turn on or off a scope channel display
        Must be 'RISE' or 'FALL'
        """
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
    def trigger_level(self, c, level = None):
        """Get or set the vertical zero position of a channel in units of divisions
        """
        dev = self.selectedDevice(c)
        if level is None:
            resp = yield dev.query('TRIG:A:LEV?')
        else:
            yield dev.write(('TRIG:A:LEV %f') %level)
            resp = yield dev.query('TRIG:A:LEV?')
        level = float(resp)
        returnValue(level)

    @setting(133, channel = '?', returns = ['s'])
    def trigger_channel(self, c, channel = None):
        """Get or set the trigger source
        Must be one of "AUX","LINE", 1, 2, 3, 4, "CH1", "CH2", "CH3", "CH4"
        """
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
    def trigger_mode(self, c, mode = None):
        """Sets or reads trigger mode
        Must be 'AUTO' or 'NORM'
        """
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.query('TRIG:A:MOD?')
        else:
            if mode not in ['AUTO','NORM']:
                raise Exception('Slope must be "AUTO" or "NORM"')
            else:
                yield dev.write('TRIG:A:MOD '+mode)
                resp = yield dev.query('TRIG:A:MOD?')
        returnValue(resp)

    @setting(151, position = 'v', returns = ['v'])
    def horiz_position(self, c, position = None):
        """Get or set the horizontal trigger position (as a percentage from the left edge of the screen)
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('HOR:POS?')
        else:
            yield dev.write(('HOR:POS %f') %position)
            resp = yield dev.query('HOR:POS?')
        position = float(resp)
        returnValue(position)

        
    
    #Data acquisition settings
    @setting(201, channel = 'i', start = 'i', stop = 'i', returns='*v[ns] {time axis} *v[mV] {scope trace}')
    def get_trace(self, c, channel, start=1, stop=10000):
        """Get a trace from the scope.
        OUTPUT - (array voltage in volts, array time in seconds)
        """
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
        voltsPerDiv = yield dev.query('CH%d:SCA?' %channel)
        secPerDiv = yield dev.query('HOR:SCA?')        
        #Transfer waveform data
        binary = yield dev.query('CURV?')
        #Parse waveform preamble
        #voltsPerDiv, secPerDiv, voltUnits, timeUnits = _parsePreamble(preamble)
        #voltUnits = 1000*m
        
        #voltUnitScaler = Value(1, voltUnits)['mV'] # converts the units out of the scope to mV
        #timeUnitScaler = Value(1, timeUnits)['ns']
        
        voltUnitScaler = 1000.0
        timeUnitScaler = 1.0e9
        #Parse binary
        trace = _parseBinaryData(binary,wordLength = wordLength)
        #Convert from binary to volts
        traceVolts = (trace * (1/32768.0) * VERT_DIVISIONS/2 * float(voltsPerDiv) - float(position) * float(voltsPerDiv) ) * voltUnitScaler
        time = numpy.linspace(0, HORZ_DIVISIONS * float(secPerDiv) * timeUnitScaler,len(traceVolts))#recordLength)

        returnValue((time, traceVolts))

def _parsePreamble(preamble):
    ###TODO: parse the rest of the preamble and return the results as a useful dictionary
    preamble = preamble.split(';')
    vertInfo = preamble[5].split(',')
    
    def parseString(string):
        number = re.sub(r'.*?([\d\.]+).*', r'\1', string)
        units = re.sub(r'.*?([a-zA-z]+)/.*', r'\1', string)
        return float(number), units
    
    voltsPerDiv, voltUnits = parseString(vertInfo[2])
    secPerDiv, timeUnits = parseString(vertInfo[3])
    return (voltsPerDiv, secPerDiv, voltUnits, timeUnits)

def _parseBinaryData(data, wordLength):
    """Parse binary data packed as string of RIBinary
    """
    formatChars = {'1':'b','2':'h'}
    formatChar = formatChars[str(wordLength)]

    #Get rid of header crap
    header = data[0:7]
    dat = data[7:]
    #unpack binary data
    if wordLength == 1:
        dat = numpy.array(unpack(formatChar*(len(dat)/wordLength),dat))
    elif wordLength == 2:
        dat = numpy.array(unpack('>' + formatChar*(len(dat)/wordLength),dat))
    return dat

__server__ = Tektronix5104BServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
