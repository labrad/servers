# Copyright (C) 2010 Daniel Sank & Julian Kelly
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
name = Tektronix TDS 5054B-NV Oscilloscope
version = 0.1
description = Talks to the Tektronix 5054B oscilloscope

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

# FYI haven't really tested functions other than get trace

from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

from struct import unpack

import numpy, re

COUPLINGS = ['AC', 'DC']
VERT_DIVISIONS = 10.0
HORZ_DIVISIONS = 10.0
SCALES = []

class Tektronix5054BWrapper(GPIBDeviceWrapper):
    pass

class Tektronix5054BServer(GPIBManagedServer):
    name = 'TEKTRONIX 5054B OSCILLOSCOPE'
    deviceName = 'TEKTRONIX TDS 5054B'
    deviceWrapper = Tektronix2014BWrapper
        
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
    @setting(21, channel = 'i', returns = '(vsvvssss)')
    def channel_info(self, c, channel):
        """channel(int channel)
        Get information on one of the scope channels.

        OUTPUT
        Tuple of (probeAtten, ?, scale, position, coupling, bwLimit, invert, units)
        """
        #NOTES
        #The scope's response to 'CH<x>?' is a string of format
        #'1.0E1;1.0E1;2.5E1;0.0E0;DC;OFF;OFF;"V"'
        #These strings represent respectively,
        #probeAttenuation;?;?;vertPosition;coupling;?;?;vertUnit

        dev = self.selectedDevice(c)
        resp = yield dev.query('CH%d?' %channel)
        probeAtten, iDontKnow, scale, position, coupling, bwLimit, invert, unit = resp.split(';')

        #Convert strings to numerical data when appropriate
        probeAtten = T.Value(float(probeAtten),'')
        #iDontKnow = None, I don't know what this is!
        scale = T.Value(float(scale),'')
        position = T.Value(float(position),'')
        coupling = coupling
        bwLimit = bwLimit
        invert = invert
        unit = unit[1:-1] #Get's rid of an extra set of quotation marks

        returnValue((probeAtten,iDontKnow,scale,position,coupling,bwLimit,invert,unit))

    @setting(22, channel = 'i', coupling = 's', returns=['s'])
    def coupling(self, c, channel, coupling = None):
        """Get or set the coupling of a specified channel
        Coupling can be "AC" or "DC"
        """
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CH%d:COUP?' %channel)
        else:
            coupling = coupling.upper()
            if coupling not in COUPLINGS:
                raise Exception('Coupling must be "AC" or "DC"')
            else:
                yield dev.write(('CH%d:COUP '+coupling) %channel)
                resp = yield dev.query('CH%d:COUP?' %channel)
        returnValue(resp)

    @setting(23, channel = 'i', scale = 'v', returns = ['v'])
    def scale(self, c, channel, scale = None):
        """Get or set the vertical scale of a channel
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('CH%d:SCA?' %channel)
        else:
            scale = format(scale,'E')
            yield dev.write(('CH%d:SCA '+scale) %channel)
            resp = yield dev.query('CH%d:SCA?' %channel)
        scale = float(resp)
        returnValue(scale)

    @setting(24, channel = 'i', factor = 'i', returns = ['s'])
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

    @setting(25, channel = 'i', state = '?', returns = '')
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
        
    
    #Data acquisition settings
    @setting(41, channel = 'i', start = 'i', stop = 'i', returns='?')
    def get_trace(self, c, channel, start=1, stop=5000):
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
        if not (start<2500 and start>0 and stop<5001 and stop>1):
            raise Exception('start/stop points out of bounds')
        yield dev.write('DAT:STAR %d' %start)
        yield dev.write('DAT:STOP %d' %stop)
        #Transfer waveform preamble
        preamble = yield dev.query('WFMP?')
        #Transfer waveform data
        binary = yield dev.query('CURV?')
        #Parse waveform preamble
        voltsPerDiv, secPerDiv = _parsePreamble(preamble)
        #Parse binary
        trace = _parseBinaryData(binary,wordLength = wordLength)
        #Convert from binary to volts
        traceVolts = trace * (1/32768.0) * VERT_DIVISIONS/2 * voltsPerDiv
        time = numpy.linspace(0,HORZ_DIVISIONS*secPerDiv,recordLength)

        returnValue((time,traceVolts))

def _parsePreamble(preamble):
    ###TODO: parse the rest of the preamble and return the results as a useful dictionary
    preamble = preamble.split(';')
    vertInfo = preamble[5].split(',')
    
    # add units to parseStr to pass into labrad 
    parseStr = lambda str: re.sub(r'.*?([\d\.]+).*', r'\1', str) # regular expressions that pull out the number from the string
    
    voltsPerDiv = float(parseStr(vertInfo[2]))
    secPerDiv = float(parseStr(vertInfo[3]))
    return (voltsPerDiv,secPerDiv)

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

__server__ = Tektronix5054BServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
