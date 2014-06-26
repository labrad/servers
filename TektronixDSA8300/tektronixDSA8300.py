# Copyright (C) 2013 Julian Kelly
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
name = Tektronix DSA 8300 Sampling Scope
version = 0.2
description = Talks to the Tektronix DSA 8300 Sampling Scope

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
from struct import unpack
from time import sleep
import numpy, re

COUPLINGS = ['AC', 'DC', 'GND']
TRIG_CHANNELS = ['AUX','CH1','CH2','CH3','CH4','LINE']
VERT_DIVISIONS = 10.0
HORZ_DIVISIONS = 10.0
SCALES = []

class TektronixDSA8300Wrapper(GPIBDeviceWrapper):
    pass

class TektronixDSA8300Server(GPIBManagedServer):
    name = 'TEKTRONIX DSA 8300 Sampling Scope'
    deviceName = 'TEKTRONIX DSA8300'
    deviceWrapper = TektronixDSA8300Wrapper
        
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
    def channel_info(self, c, channel):
        """channel(int channel)
        Get information on one of the scope channels.

        OUTPUT
        Tuple of (probeAtten, termination, scale, position, coupling, bwLimit, invert, units)
        """
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

    @setting(113, averages='?', returns = '?')
    def average(self, c, averages = None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if averages is None:
            resp = yield dev.query('ACQ:NUMAV?')
        else:
            if averages>1:
                yield dev.write('ACQ:MOD AVER')
                yield dev.write('ACQ:NUMAV %d' % averages)
                resp = yield dev.query('ACQ:NUMAV?')
            if averages==1:
                yield dev.write('ACQ:MOD SAM')
                yield dev.write('ACQ:NUMAV %d' % averages)
                resp = yield dev.query('ACQ:NUMAV?')
        averages = float(resp)
        returnValue(averages)

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
        
    @setting(115, length='?', returns = '?')
    def record_length(self, c, length = 16000):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if length is None:
            resp = yield dev.query('HOR:MAI:REC?')
        else:
            yield dev.write(('HOR:MAI:REC '+str(length)))
            resp = yield dev.query('HOR:MAI:REC?')
        length = float(resp)
        returnValue(length)

    @setting(117, channel = 'i', position = 'v', returns = ['v'])
    def position(self, c, channel, position = None):
        """Get or set the vertical zero position of a channel
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('CH%d:POS?' %channel)
        else:
            yield dev.write(('CH%d:POS %f') %(channel,position))
            resp = yield dev.query('CH%d:POS?' %channel)
        position = float(resp)
        returnValue(position)

    @setting(131, returns = ['s'])
    def trigger_source(self, c, source=None):
        """Set the trigger sounce, choose between
        C1CLKRec, C3CLCKRec, EXTDirect, EXTPrescaler, FREerun, INTClk, TDR
        """
        dev = self.selectedDevice(c)
        if source is None:
            resp = yield dev.query('TRIG:SOU?')
        else:
            yield dev.write('TRIG:SOU '+source)
            resp = yield dev.query('TRIG:SOU?')
        returnValue(resp)
        
    @setting(132, level = 'v', returns = ['v'])
    def trigger_level(self, c, level = None):
        """Get or set the vertical zero position of a channel in units of divisions
        """
        dev = self.selectedDevice(c)
        if level is None:
            resp = yield dev.query('TRIG:LEV?')
        else:
            yield dev.write(('TRIG:LEV %f') %level)
            resp = yield dev.query('TRIG:LEV?')
        level = float(resp)
        returnValue(level)

    @setting(151, position = 'v', returns = ['v'])
    def horizontal_position(self, c, position = None):
        """Get or set the horizontal trigger position (as a percentage from the left edge of the screen)
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('HOR:MAI:POS?')
        else:
            yield dev.write(('HOR:MAI:POS '+str(position)))
            resp = yield dev.query('HOR:MAI:POS?')
        position = float(resp)
        returnValue(position)

    @setting(152, channel='i', scale = 'v', returns = ['v'])
    def vertical_scale(self, c, channel, scale = None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('CH%d:SCA?'%channel)
        else:
            yield dev.write('CH%d:SCA %f' %(channel,scale))
            resp = yield dev.query('CH%d:SCA?'%channel)
        scale = float(resp)
        returnValue(scale)
        
    @setting(153, scale = 'v', returns = ['v'])
    def horizontal_scale(self, c, scale = None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('HOR:MAI:SCA?')
        else:
            yield dev.write(('HOR:MAI:SCA '+str(scale)))
            resp = yield dev.query('HOR:MAI:SCA?')
        scale = float(resp)
        returnValue(scale)
        
    
    #Data acquisition settings
    @setting(201, channel = 'i', start = 'i', stop = 'i', record_length='i', numavg='i', returns='*v[ns] {time axis} *v[mV] {scope trace}')
    def get_trace(self, c, channel, start=1, stop=16000, record_length = 16000, numavg=128):
        """Get a trace from the scope.
        OUTPUT - (array voltage in volts, array time in seconds)
        record_length can be 50, 100, 250, 500, 1000, 2000, 4000, 8000, 16000
        
        FIXME:  This currently takes as a parameter and sets the number of averages.  It should instead
        respect the number of averages set by self.average().  I think the scope can be made
        to do this by fiddling with the ACQUIRE:STOPAFTER series of commands.  -- ERJ
        """
##        DATA ENCODINGS
##        RIB - signed, MSB first
##        RPB - unsigned, MSB first
##        SRI - signed, LSB first
##        SRP - unsigned, LSB first
        wordLength = 4 #Hardcoding to set data transer word length to 4 bytes
        recordLength = stop-start+1
        
        dev = self.selectedDevice(c)
        yield dev.write('ACQUIRE:STATE OFF')
        #DAT:SOU - set waveform source channel
        yield dev.write('DAT:SOU CH%d' %channel)
        #DAT:ENC - data format (binary/ascii)
        yield dev.write('DAT:ENC ASCI')
        yield dev.write('ACQUIRE:MODE AVERAGE')
        yield dev.write('ACQUIRE:NUMAVG %d' % numavg)
        yield dev.write('ACQUIRE:STOPAFTER COUNT %d' % numavg)
        yield dev.write('ACQUIRE:STOPAFTER:MODE CONDITION')
        #yield dev.write('ACQUIRE:STOPAFTER:CONDITION AVGComp')
        yield dev.write('ACQUIRE:DATA:CLEAR')
        
        #Starting and stopping point
        yield dev.write('DAT:STAR %d' %start)
        yield dev.write('DAT:STOP %d' %stop)
        yield dev.write('HOR:MAI:REC %d' %record_length)
        #Transfer waveform preamble
        position = yield dev.query('HOR:MAI:POS?') # in units of divisions
        yield dev.write('ACQUIRE:STATE ON')
        while True:
            busy = yield dev.query('BUSY?')
            if '1' in busy:
                sleep(2)
            else:
                break     
        #Transfer waveform data
        stringData = yield dev.query('CURV?')
        trace = numpy.array(stringData.split(','), dtype='float')
        preamble = yield dev.query('WFMO?') # the preamble is always from the LAST curve sent
        # so its important that CURV? comes BEFORE WFMO?
        #Parse waveform preamble
        voltsPerDiv, secPerDiv, voltUnits, timeUnits = _parsePreamble(preamble)
        voltUnitScaler = Value(1, voltUnits)['mV'] # converts the units out of the scope to mV
        timeUnitScaler = Value(1, timeUnits)['ns']
        #Convert from binary to volts
        yUnit = yield dev.query('WFMO:YUNIT?')
        yUnit = re.search(r'"(.*?)"',yUnit).groups()[0]
        yUnit = Value(1.0, yUnit)
        yScale = yield dev.query('WFMO:YSCALE?')
        yScale = float(yScale)
        #traceVolts = (trace * (1/(2.**25)) * VERT_DIVISIONS/2 * voltsPerDiv - float(position) * voltsPerDiv) * voltUnitScaler
        traceVolts = trace*yUnit*yScale
        time = numpy.linspace(0, HORZ_DIVISIONS * secPerDiv * timeUnitScaler,len(traceVolts))#recordLength)

        returnValue((time, traceVolts))

def _parsePreamble(preamble):
    ###TODO: parse the rest of the preamble and return the results as a useful dictionary
    preamble = preamble.split(';')
    vertInfo = preamble[-2].split(',')
    
    def parseString(string): # use 'regular expressions' to parse the string
        number = re.sub(r'.*?([\d\.]+).*', r'\1', string)
        units = re.sub(r'.*?([a-zA-z]+)/.*', r'\1', string)
        return float(number), units
    
    voltsPerDiv, voltUnits = parseString(vertInfo[1])
    secPerDiv, timeUnits = parseString(vertInfo[2])
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
    elif wordLength == 4:
        raise Exception("you really need to implement this")
    return dat

__server__ = TektronixDSA8300Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
