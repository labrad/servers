# Copyright (C) 2013 Rami Barends
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
name = Agilent 7104B Oscilloscope
version = 0.1
description = Talks to the Agilent 7104B oscilloscope

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

import numpy, re

COUPLINGS = ['AC', 'DC']
TRIG_CHANNELS = ['EXT','CHAN1','CHAN2','CHAN3','CHAN4','LINE']
VERT_DIVISIONS = 8.0
HORZ_DIVISIONS = 20.0
SCALES = []

class Agilent7104BWrapper(GPIBDeviceWrapper):
    pass

class Agilent7104BServer(GPIBManagedServer):
    name = 'AGILENT DSO 7104B OSCILLOSCOPE'
    deviceName = 'AGILENT TECHNOLOGIES DSO7104B'
    deviceWrapper = Agilent7104BWrapper
        
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
        dev = self.selectedDevice(c)
        resp = yield dev.query(':CHAN%d?' %channel)
        #example of resp:
        #a=':CHAN1:RANG +40.0E+00;OFFS +0.00000E+00;COUP DC;IMP ONEM;DISP 1;BWL 0;INV 0;LAB "1";UNIT VOLT;PROB +10E+00;PROB:SKEW +0.00E+00;STYP SING'
        vals=[]
        for part in resp.split(';'):
            vals.append( part.split(' ')[1] ) # the last part contains the numbers
        scale=vals[0]
        position=vals[1]
        coupling=vals[2]
        termination=vals[3]
        if termination=='ONEM':
            termination=1e6
        else:
            termination=50
        bwLimit=vals[5]            
        invert=vals[6]
        unit=vals[8]
        probeAtten=vals[9]
        #Convert strings to numerical data when appropriate
        probeAtten = T.Value(float(probeAtten),'')
        termination = T.Value(float(termination),'')
        scale = T.Value(float(scale),'')
        position = T.Value(float(position),'')
        coupling = coupling
        bwLimit = T.Value(float(bwLimit),'')
        invert = invert
        returnValue((probeAtten,termination,scale,position,coupling,bwLimit,invert,unit))

    @setting(111, channel = 'i', coupling = 's', returns=['s'])
    def coupling(self, c, channel, coupling = None):
        """Get or set the coupling of a specified channel
        Coupling can be "AC", "DC", or "GND"
        """
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CHAN%d:COUP?' %channel)
        else:
            coupling = coupling.upper()
            if coupling not in COUPLINGS:
                raise Exception('Coupling must be "AC", "DC"')
            else:
                yield dev.write(('CHAN%d:COUP '+coupling) %channel)
                resp = yield dev.query('CHAN%d:COUP?' %channel)
        returnValue(resp)

    @setting(112, channel = 'i', scale = 'v', returns = ['v'])
    def scale(self, c, channel, scale = None):
        """Get or set the vertical scale per div of a channel in Volts
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query(':CHAN%d:SCAL?' %channel)
        else:
            scale = format(scale['V'],'E')
            yield dev.write((':CHAN%d:SCAL '+scale+' V') %channel)
            resp = yield dev.query(':CHAN%d:SCAL?' %channel)
        scale = (Value(float(resp),'V'))
        returnValue(scale)

    @setting(113, channel = 'i', factor = 'i', returns = ['s'])
    def probe(self, c, channel, factor = None):
        """Get or set the probe attenuation factor.
        """
        probeFactors = [1,10,20,50,100,500,1000]
        dev = self.selectedDevice(c)
        chString = ':CHAN%d' %channel
        if factor is None:
            resp = yield dev.query(chString+':PROB?')
        elif factor in probeFactors:
            yield dev.write(chString+':PROB%d' %factor)
            resp = yield dev.query(chString+':PROB?')
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
        if state not in [0,1,'OFF','ON']:
            raise Exception('state must be 0, 1, OFF, ON')
        if isinstance(state, int):
            state = str(state)
        yield dev.write((':CHAN%d:DISP '+state) %channel)

    @setting(115, channel = 'i', invert = 'i', returns = ['i'])
    def invert(self, c, channel, invert = None):
        """Get or set the inversion status of a channel
        """
        dev = self.selectedDevice(c)
        if invert is None:
            resp = yield dev.query(':CHAN%d:INV?' %channel)
        else:
            yield dev.write((':CHAN%d:INV %d') %(channel,invert))
            resp = yield dev.query(':CHAN%d:INV?' %channel)
        invert = int(resp)
        returnValue(invert)

    @setting(116, channel = 'i', termination = 'v', returns = ['v'])
    def termination(self, c, channel, termination = None):
        """Get or set the a channels termination
        Can be 50 or 1E+6
        """
        dev = self.selectedDevice(c)
        if termination is None:
            resp = yield dev.query(':CHAN%d:IMP?' %channel)
        elif termination in [50,1e6]:
            if termination==50:
                term='FIFT'
            else:
                term='ONEM'                
            yield dev.write((':CHAN%d:IMP %s') %(channel,term))
            resp = yield dev.query(':CHAN%d:IMP?' %channel)
        else:
            raise Exception('Termination must be 50 or 1E+6')
        if resp=='FIFT':
            resp=50
        else:
            resp=1e6            
        termination = float(resp)
        returnValue(termination)

    @setting(117, channel = 'i', position = 'v', returns = ['v'])
    def position(self, c, channel, position = None):
        """Get or set the vertical zero position of a channel in units of divisions - for compatibility with tek-oriented code
        """
        dev = self.selectedDevice(c)
        #first: get vertical scale        
        resp = yield dev.query(':CHAN%d:SCAL?' %channel)
        scale = (Value(float(resp),'V'))
        if position is None:
            resp = yield dev.query(':CHAN%d:OFFS?' %channel)
        else:
            pos=position*scale
            yield dev.write((':CHAN%d:OFFS %f V') %(channel,pos))
            resp = yield dev.query(':CHAN%d:OFFS?' %channel)
        position = float(resp)/float(scale)
        returnValue(position)

    '''
    @setting(117, channel = 'i', position = 'v', returns = ['v'])
    def position(self, c, channel, position = None):
        """Get or set the vertical zero position of a channel in Volts
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query(':CHAN%d:OFFS?' %channel)
        else:
            yield dev.write((':CHAN%d:OFFS %f V') %(channel,position))
            resp = yield dev.query(':CHAN%d:OFFS?' %channel)
        position = float(resp)
        returnValue(position)        
    '''
    
    @setting(131, slope = 's', returns = ['s'])
    def trigger_slope(self, c, slope = None):
        """Turn on or off a scope channel display
        Must be 'RISE' or 'FALL'
        only edge triggering is implemented here
        """
        dev = self.selectedDevice(c)
        if slope is None:
            resp = yield dev.query(':TRIG:EDGE:SLOP?')
        else:
            slope = slope.upper()
            if slope not in ['RISE','FALL','POS','NEG']:
                raise Exception('Slope must be "RISE" , "FALL", "POS", "NEG" ')
            else:
                if slope=='RISE':
                    slope='POS'
                else:
                    slope='NEG'
                yield dev.write(':TRIG:EDGE:SLOP '+slope)
                resp = yield dev.query(':TRIG:EDGE:SLOP?')
        returnValue(resp)

    @setting(132, level = 'v', returns = ['v'])
    def trigger_level(self, c, level = None):
        """Get or set the vertical zero position of a channel in voltage
        """
        dev = self.selectedDevice(c)
        if level is None:
            resp = yield dev.query(':TRIG:EDGE:LEV?')
        else:
            yield dev.write((':TRIG:EDGE:LEV %f') %level['V'])
            resp = yield dev.query(':TRIG:EDGE:LEV?')
        level = Value(float(resp),'V')
        returnValue(level)

    @setting(133, channel = '?', returns = ['s'])
    def trigger_channel(self, c, channel = None):
        """Get or set the trigger source
        Must be one of "EXT","LINE", 1, 2, 3, 4, CHAN1, CHAN2...
        """
        dev = self.selectedDevice(c)
        if channel in ['CH1','CH2','CH3','CH4']:
            channel=int(channel[2]) #just get the number, below we make it compatible    
        if isinstance(channel, str):
            channel = channel.upper()
        if isinstance(channel, int):
            channel = 'CHAN%d' %channel            
        if channel is None:
            resp = yield dev.query(':TRIG:EDGE:SOUR?')
        elif channel in TRIG_CHANNELS:
            yield dev.write(':TRIG:EDGE:SOUR '+channel)
            resp = yield dev.query(':TRIG:EDGE:SOUR?')
        else:
            raise Exception('Select valid trigger channel')
        returnValue(resp)

    @setting(151, position = 'v', returns = ['v'])
    def horiz_position(self, c, position = None):
        """Get or set the horizontal trigger position in seconds from the trigger
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query(':TIM:POS?')
        else:
            yield dev.write((':TIM:POS %f') %position)
            resp = yield dev.query(':TIM:POS?')
        position = float(resp)
        returnValue(position)

    @setting(152, scale = 'v', returns = ['v'])
    def horiz_scale(self, c, scale = None):
        """Get or set the horizontal scale value in s per div
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query(':TIM:SCAL?')
        else:
            scale = format(scale,'E')
            yield dev.write(':TIM:SCAL '+scale)
            resp = yield dev.query(':TIM:SCAL?')
        scale = float(resp)
        returnValue(scale)
        
    
    #Data acquisition settings
    @setting(201, channel = 'i', returns='*v[ns] {time axis} *v[mV] {scope trace}')
    def get_trace(self, c, channel):
        """Get a trace from the scope.
        OUTPUT - (array voltage in volts, array time in seconds)
        removed start and stop: start = 'i', stop = 'i' (,start=1, stop=10000)
        """
        wordLength = 2 #Hardcoding to set data transer word length to 2 bytes
        recordLength = stop-start+1
        
        dev = self.selectedDevice(c)

        #set waveform source channel
        yield dev.write(':WAV:SOUR CHAN%d' %channel)
        # data format (binary/ascii)
        yield dev.write(':WAV:FORM WORD')
        #Starting and stopping point
        #yield dev.write('DAT:STAR %d' %start)
        #yield dev.write('DAT:STOP %d' %stop)
        #Transfer waveform preamble
        preamble = yield dev.query(':WAV:PRE?')
        position = yield dev.query(':TIM:POS?')
        #run:
        yield dev.write(':SING')
        #Transfer waveform data      
        binary = yield dev.query(':WAV:DATA?')
        #Parse waveform preamble
        points,xincrement,xorigin,xreference,yincrement,yorigin,yreference,vsteps = _parsePreamble(preamble)
        
        voltUnitScaler = 1 #Value(1, voltUnits)['V'] # converts the units out of the scope to V
        timeUnitScaler = 1 #Value(1, timeUnits)['s']
        #Parse binary
        trace = _parseBinaryData(binary,wordLength = wordLength)
        trace = trace[-points:]

        #Convert from binary to volts
        traceVolts = (trace - yreference) * yincrement * voltUnitScaler
        time = (numpy.arange(points)*xincrement + xorigin) * timeUnitScaler
        returnValue((time, traceVolts))

def _parsePreamble(preamble):
    '''
    Check 
    <preamble_block> ::= <format 16-bit NR1>,
                     <type 16-bit NR1>,
                     <points 32-bit NR1>,
                     <count 32-bit NR1>,
                     <xincrement 64-bit floating point NR3>,
                     <xorigin 64-bit floating point NR3>,
                     <xreference 32-bit NR1>,
                     <yincrement 32-bit floating point NR3>,
                     <yorigin 32-bit floating point NR3>,
                     <yreference 32-bit NR1>    
    '''
    #fields=unpack( '>IILLddLffL' ,  preamble)
    fields=preamble.split(',')
    vsteps=65536.0
    points=int(fields[2])
    yincrement=float(fields[7])
    yorigin=float(fields[8])
    yreference=int(fields[9])  
    xincrement=float(fields[4])
    xorigin=float(fields[5])
    xreference=int(fields[6])
    return (points,xincrement,xorigin,xreference,yincrement,yorigin,yreference,vsteps)

def _parseBinaryData(data, wordLength):
    """Parse binary data packed as string of RIBinary
    """
    formatChars = {'1':'B','2':'H'}
    formatChar = formatChars[str(wordLength)]
    dat = data
    #unpack binary data
    if wordLength == 1:
        dat = numpy.array(unpack(formatChar*(len(dat)/wordLength),dat))
    elif wordLength == 2:
        dat = numpy.array(unpack('>' + formatChar*(len(dat)/wordLength),dat))
    return dat

__server__ = Agilent7104BServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
