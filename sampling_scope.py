#!c:\python25\python.exe

# Copyright (C) 2007  Matthew Neeley, Max Hofheinz
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

from labrad import types as T, errors, util
from labrad.server import setting
from labrad.gpib import GPIBDeviceServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import struct
import re

__QUERY__ = 'ENC WAV:BIN;BYT. LSB;OUT TRA%d;WAV?'

class NotConnectedError(errors.Error):
    """You need to connect"""
    code = 10

class InvalidChannelError(errors.Error):
    """Only channels 1 through 8 are valid"""
    code = 10

class MeasurementError(errors.Error):
    """Scope returned error"""
    code = 10

class OutofrangeError(errors.Error):
    """Signal is out of range"""
    code = 10

class SendTraceError(errors.Error):
    """StrList needs to have either 3 or 4 elements"""
    code = 11
    

TIMEOUT = 120


class SamplingScopeDevice(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        yield self.timeout(TIMEOUT)


class SamplingScope(GPIBDeviceServer):
    name = 'Sampling Scope'
    deviceName = 'Tektronix 11801C'
    deviceWrapper = SamplingScopeDevice

    @setting(10, 'Get Trace',
                 trace=[': Query TRACE1',
                        'w: Specify trace to query: 1, 2, or 3'],
                 returns=['*v: y-values', 'v: x-increment'])
    def get_trace(self, c, trace=1):
        """Returns the y-values of the current trace from the sampling scope.
        
        First element: offset time
        Second element: time step
        Third to last element: trace
        """
        dev = self.selectedDevice(c)
        if trace < 1 or trace > 3:
            raise NotConnectedError()
        yield dev.write('COND TYP:AVG')
        
        while True:
            if int((yield dev.query('COND? REMA'))[18:]) == 0:
                break
            yield util.wakeupCall(2)

        resp = yield dev.query(__QUERY__ % trace, bytes=20000L)
        vals = _parseBinaryData(resp)
        returnValue([T.Value(v, 'V') for f in vals])
    
    @setting(241, 'Send Trace To Dataserver',
                  server=['s'], session=['s'], dataset=['s'], trace=['w'],
                  returns=['s: Dataset Name'])
    def send_trace(self, c, server, session, dataset, trace=1):
        """Send the current trace to the data vault.
        """
        dev = self.selectedDevice(c)

        resp = yield dev.query(__QUERY__ % trace, bytes=20000L)
        vals = _parseBinaryData(resp)

        startx = vals[0]
        stepx = vals[1]
        vals = vals[2:]

        out = [[(startx + i*stepx)*1e9, d] for i, d in enumerate(vals)]
        ds = self.client[server]
        p = ds.packet()
        p.open_session(session)
        p.new_dataset(dataset)
        p.add_independent_variable('time', 'ns')
        p.add_dependent_variable('amplitude', 'V')
        p.add_parameter('Trace', trace)
        p.add_data(out)
        resp = yield p.send()
        name = resp.new_dataset
        returnValue(name)

 
    @setting(101, 'Record Length',
                  data=['w: Record Length 512, 1024, 2048 or 4096, 5120'],
                  returns=['v[s]: Start Time'])
    def record_length(self, c, data):
        """Sets the start time of the trace."""
        dev = self.selectedDevice(c)
        yield dev.write('TBM LEN:%d' % data)
        returnValue(data)

    @setting(102, 'Mean',
                  channel=['w: Trace number', ': Trace 1'],
                  returns=['v[V]: Time average of the trace'])
    def mean(self, c, channel=1):
        dev = self.selectedDevice(c)
        s = yield dev.query('COND TYP:AVG;SEL TRA%d;COND WAIT;MEAN?' % channel)
        if s[-2:] in ['GT', 'LT', 'OR']:
            raise OutofrangeError()
        returnValue(T.Value(float(s[5:-3]), 'V'))

    @setting(103, 'Amplitude',
                  channel=['w: Trace number', ': Trace 1'],
                  returns=['v[V]: Time average of the trace'])
    def amplitude(self, c, channel=1):
        dev = self.selectedDevice(c)
        s = yield dev.query('SEL TRA%d;PP?' % channel) # 'COND TYP:AVG;SEL TRA%d;COND WAIT;AMP?'
        if s[-2:] in ['GT', 'LT', 'OR']:
            raise OutofrangeError()
        returnValue(T.Value(float(s[3:-3]), 'V'))
        
    @setting(11, 'Start Time',
                 data=['v[s]: Set Start Time'],
                 returns=['v[s]: Start Time'])
    def start_time(self, c, data):
        """Sets the start time of the trace."""
        dev = self.selectedDevice(c)
        yield dev.write('MAINP %g' % data.value)
        returnValue(data)

    @setting(12, 'Time Step',
                 data=['v[s]: Set Time Step'],
                 returns=['v[s]: Time Step'])
    def time_step(self, c, data):
        """Sets the time/div for of the trace."""
        dev = self.selectedDevice(c)
        yield dev.write('TBM TIM:%g' % data.value)
        #yield dev.write('TBW TIM:%g' % data.value)
        #yield dev.write('TBM TIM:%g' % data.value)
        returnValue(data)


    @setting(112, 'Offset',
                  data=['v[V]: Set offset (voltage at screen center)'],
                  returns=['v[V]: offset'])
    def offset(self, c, data):
        """Set offset, i.e. the voltage at the center of the screen."""
        dev = self.selectedDevice(c)
        yield dev.write('CHM%d OFFS:%g' % (self.getchannel(c), data.value))
        returnValue(data)


    @setting(13, 'Sensitivity',
                 data=['v[V]: Set V/div'],
                 returns=['v[V]: Sensitivity'])
    def sensitivity(self, c, data):
        """Set sensitivity (V/div)."""
        dev = self.selectedDevice(c)
        yield dev.write('CHM%d SENS:%g' % (self.getchannel(c), data))
        returnValue(data)

        

    def getchannel(self, c):
        return c.get('Channel', 1)
    

    @setting(113, 'Channel',
                  data=[': Select Channel 1',
                        'w: Channel (1 to 8)'],
                  returns=['w: Sensitivity'])
    def channel(self, c, data=1):
        """Select channel."""
        if data < 1 or data > 8:
            raise InvalidChannelError()
        c['Channel'] = data
        return data


    @setting(114, 'Average', averages=['w'], returns=['w'])
    def average(self, c, averages=1):
        """Set number of averages."""
        dev = self.selectedDevice(c)
        yield dev.write('AVG OFF')
        if averages > 1:
            yield dev.write('NAV %d' % averages)
            yield dev.write('AVG ON')
        returnValue(averages)
     
 
    @setting(14, 'trace',
                 trace=[': Attach selected channel to trace 1',
                        'w: Attach selected channel to a trace'],
                 returns=[': Trace'])
    def trace(self, c, trace=1):
        """Define a trace."""
        dev = self.selectedDevice(c)
        yield dev.write("TRA%d DES:'M%d'" % (trace, self.getchannel(c)))
        yield dev.write('SEL TRA%d' % trace)
        returnValue(trace)

 
    @setting(15, 'Trigger Level',
                 data=['v[V]: Set trigger level'],
                 returns=['v[V]: Trigger level'])
    def trigger_level(self, c, data):
        """Set trigger level."""
        dev = self.selectedDevice(c)
        yield dev.write('TRI LEV:%g' % data.value)
        returnValue(data)
   
    @setting(16, 'Trigger positive', returns=[''])
    def trigger_positive(self, c):
        """Trigger on positive slope."""
        dev = self.selectedDevice(c)
        yield dev.write('TRI SLO:PLU')
          
    @setting(17, 'Trigger negative', returns=[''])
    def trigger_negative(self, c):
        """Trigger on negative slope."""
        dev = self.selectedDevice(c)
        yield dev.write('TRI SLO:NEG')

    @setting(18, 'Reset', returns=[''])
    def reset(self, c):
        """Reset to default state."""
        dev = self.selectedDevice(c)
        yield dev.write('INI')

        
_xzero = re.compile('XZERO:(-?\d*.?\d+E?-?\+?\d*),')
_xincr = re.compile('XINCR:(-?\d*.?\d+E?-?\+?\d*),')
_yzero = re.compile('YZERO:(-?\d*.?\d+E?-?\+?\d*),')
_ymult = re.compile('YMULT:(-?\d*.?\d+E?-?\+?\d*),')
    
def _parseBinaryData(data):
    """Parse the data coming back from the scope"""
    hdr, dat = data.split(';CURVE')
    dat = dat[dat.find('%')+3:-1]
    dat = struct.unpack('h'*(len(dat)/2), dat)
    xzero = float(_xzero.findall(hdr)[0])
    xincr = float(_xincr.findall(hdr)[0])
    yzero = float(_yzero.findall(hdr)[0])
    ymult = float(_ymult.findall(hdr)[0])

    return [xzero, xincr] + [d*ymult + yzero for d in dat]


__server__ = SamplingScope()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
