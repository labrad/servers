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
version = 0.2.1
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
import numpy as np

COUPLINGS = ['AC', 'DC', 'GND']
TRIG_CHANNELS = ['AUX', 'CH1', 'CH2', 'CH3', 'CH4', 'LINE']
VERT_DIVISIONS = 8.0
HORZ_DIVISIONS = 10.0
SCALES = []


class AgilentDSO91304AServer(GPIBManagedServer):
    name = 'Agilent Infiniium Oscilloscope'
    deviceName = ['Agilent Technologies DSO91304A',
                  'KEYSIGHT TECHNOLOGIES DSO90804A']

    @setting(11, returns=[])
    def reset(self, c):
        dev = self.selectedDevice(c)
        yield dev.query('*RST;*OPC?')
        # TODO wait for reset to complete

    @setting(12, returns=[])
    def clear_buffers(self, c):
        dev = self.selectedDevice(c)
        yield dev.query('*CLS;*OPC?')

    #Channel settings
    @setting(100, channel='i', returns='(vvvvsvss)')
    def channel_infoNONEXISTANT(self, c, channel):
        """channel(int channel)
        Get information on one of the scope channels.

        OUTPUT
        Tuple of (probeAtten, termination, scale, position, coupling, bwLimit, invert, units)
        """
        raise Exception('Not yet implemented')
        """
        NOTES
        The scope's response to 'CH<x>?' is a string of format
        '1.0E1;1.0E1;2.5E1;0.0E0;DC;OFF;OFF;"V"'
        These strings represent respectively,
        probeAttenuation;termination;vertScale;vertPosition;coupling;
        bandwidthLimit;invert;vertUnit
        """

        dev = self.selectedDevice(c)
        resp = yield dev.query('CH{}?'.format(channel))
        bwLimit, coupling, deskew, offset, invert, position, scale,\
        termination, probeCal, probeAtten, resistance, unit, textID,\
        textSN, extAtten, extUnits, textLabel, xPos, yPos = resp.split(';')

        # Convert strings to numerical data when appropriate
        probeAtten = T.Value(float(probeAtten), '')
        termination = T.Value(float(termination), '')
        scale = T.Value(float(scale), '')
        position = T.Value(float(position), '')
        coupling = coupling
        bwLimit = T.Value(float(bwLimit), '')
        invert = invert
        unit = unit[1:-1]  # Get's rid of an extra set of quotation marks

        returnValue((probeAtten, termination, scale, position, coupling,
                     bwLimit, invert, unit))

    @setting(111, channel='i', coupling='s', returns=['s'])
    def couplingNONEXISTANT(self, c, channel, coupling = None):
        """Get or set the coupling of a specified channel

        Coupling can be "AC", "DC", or "GND"
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CH{}:COUP?'.format(channel))
        else:
            coupling = coupling.upper()
            if coupling not in COUPLINGS:
                raise Exception('Coupling must be "AC", "DC", or "GND"')
            else:
                yield dev.write('CH{}:COUP {}'.format(channel, coupling))
                resp = yield dev.query('CH{}:COUP?'.format(channel))
        returnValue(resp)

    @setting(112, channel='i', scale='v', returns=['v'])
    def scale(self, c, channel, scale=None):
        """Get or set the vertical scale of a channel in voltage per division.
        """
        dev = self.selectedDevice(c)
        if scale is not None:
            scale = format(scale, 'E')
            yield dev.write('CHAN{}:SCAL {}'.format(channel, scale))
        resp = yield dev.query('CHAN{}:SCAL?'.format(channel))
        scale = float(resp)
        returnValue(scale)

    @setting(113, channel='i', factor='i', returns=['s'])
    def probeNONEXISTANT(self, c, channel, factor=None):
        """Get or set the probe attenuation factor.
        """
        raise Exception('Not yet implemented')
        probe_factors = [1, 10, 20, 50, 100, 500, 1000]
        dev = self.selectedDevice(c)
        ch_string = 'CH{}:'.format(channel)
        if factor is None:
            resp = yield dev.query('{}PRO?'.format(ch_string))
        elif factor in probeFactors:
            yield dev.write('{}PRO {}'.format(ch_string, factor))
            resp = yield dev.query('{}PRO?'.format(chString))
        else:
            raise Exception('Probe attenuation factor '
                            'not in {}'.format(probe_factors))
        returnValue(resp)

    @setting(114, channel='i', state='?', returns='s')
    def channelOnOff(self, c, channel, state=None):
        """Turn on or off a scope channel display.

        State must be in [0,1,'ON','OFF'].
        Channel must be int.
        If state is not specified, will return state of channel.
        """
        dev = self.selectedDevice(c)
        if state is None:
            resp = yield dev.query('CHAN{}:DISP?'.format(channel))
        else:
            if isinstance(state, int):
                state = str(state)
            elif isinstance(state, str):
                state = state.upper()
            else:
                raise Exception('state must be int or string')
            if state not in ['0', '1', 'ON', 'OFF']:
                raise Exception('state must be 0, 1, "ON", or "OFF"')
            yield dev.write('CHAN{}:DISP {}'.format(channel, state))
            resp = yield dev.query('CHAN{}:DISP?'.format(channel))
        returnValue(resp)

    @setting(115, channel='i', invert='i', returns=['i'])
    def invertNONEXISTANT(self, c, channel, invert=None):
        """Get or set the inversion status of a channel
        """
        raise Exception('Not yet implemented')
        dev = self.selectedDevice(c)
        if invert is None:
            resp = yield dev.query('CH{}:INV?'.format(channel))
        else:
            yield dev.write('CH{}:INV {}'.format(channel, invert))
            resp = yield dev.query('CH{}:INV?'.format(channel))
        invert = int(resp)
        returnValue(invert)

    @setting(117, channel='i', position='v', returns=['v'])
    def position(self, c, channel, position=None):
        """Get or set the voltage at the center of the screen
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('CHAN{}:OFFS?'.format(channel))
        else:
            yield dev.write('CHAN{}:OFFS {}'.format(channel, position))
            resp = yield dev.query('CHAN{}:OFFS?'.format(channel))
        position = float(resp)
        returnValue(position)
        
    @setting(118, mode=['s', 'i', 'b'], returns=['s'])
    def averagemode(self, c, mode=None):
        """Get or set acquisition mode
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            if mode is not None:
                if isinstance(mode, str):
                    mode = {'ON': 1, 'OFF': 0}[mode]
                elif isinstance(mode, bool):
                    mode = int(mode)
                elif isinstance(mode, int):
                    pass       
            yield dev.write('ACQ:AVER {}'.format(mode))
        resp = yield dev.query('ACQ:AVER?')
        returnValue(resp) 
        
    @setting(119, navg='i', returns=['i'])
    def numavg(self, c, navg=None):
        """Get or set number of averages
        """
        dev = self.selectedDevice(c)
        if navg is None:
            resp = yield dev.query('ACQ:COUN?')
        else:
            yield dev.write('ACQ:COUN {}'.format(navg))
            resp = yield dev.query('ACQ:COUN?')
        navg_out = int(resp)
        returnValue(navg_out)

    @setting(131, channel='i', level='v', returns='v{level}')
    def trigger_at(self, c, channel, level=None):
        """Get or set the trigger source and voltage for edge mode triggering.

        Channel must be one of 0 (AUX), 1, 2, 3, 4, or 5 (LINE).
        If trigger source is 5 (LINE) the level will be ignored
        """
        dev = self.selectedDevice(c)
        if channel not in [0, 1, 2, 3, 4, 5]:
            raise ValueError('Invalid trigger channel: {}'
                             'Valid channels are [0, 1, 2, 3, 4, 5]'
                             '0 for AUX, 5 for LINE'.format(channel))
        if channel == 0:
            channel = 'AUX'
        elif channel == 5:
            channel = 'LINE'
        elif isinstance(channel, int):
            channel = 'CHAN{}'.format(channel)
        yield dev.write('TRIG:EDGE:SOUR {}'.format(channel))
        if channel != 'LINE':
            yield dev.write('TRIG:LEV {}, {}'.format(channel, level))
            # set trigger level
            resp = yield dev.query('TRIG:LEV? {}'.format(channel))
        else:
            resp = 0.0
        level = float(resp)
        returnValue(level)

    @setting(132, slope='s', returns=['s'])
    def trigger_mode(self, c, slope=None):
        """Change trigger mode. Use 'EDGE' for edge triggering.

        Must be one of 'COMM', 'DEL', 'EDGE', 'GLIT', 'PATT', 'PWID', 'RUNT',
        'SEQ', ',SHOL', 'STAT', 'TIM', 'TRAN', 'TV', ',WIND', 'SBUS1', 'SBUS2',
        'SBUS3', 'SBUS4'.
        """
        dev = self.selectedDevice(c)
        if slope is None:
            resp = yield dev.query('TRIG:MODE?')
        else:
            slope = slope.upper()
            if slope not in ['COMM', 'DEL', 'EDGE', 'GLIT', 'PATT', 'PWID',
                             'RUNT', 'SEQ', ',SHOL', 'STAT', 'TIM', 'TRAN',
                             'TV', ',WIND', 'SBUS1', 'SBUS2', 'SBUS3', 'SBUS4']:
                raise Exception('Slope must be valid type.')
            else:
                yield dev.write('TRIG:MODE {}'.format(slope))
                resp = yield dev.query('TRIG:MODE?')
        returnValue(resp)

    @setting(133, slope='s', returns=['s'])
    def trigger_edge_slope(self, c, slope=None):
        """Change trigger edge slope.

        Must be 'POS,' 'NEG', or 'EITH'er
        """
        dev = self.selectedDevice(c)
        if slope is None:
            resp = yield dev.query('TRIG:EDGE:SLOP?')
        else:
            slope = slope.upper()
            if slope not in ['POS', 'NEG', 'EITH']:
                raise Exception('Slope must be "RISE" or "FALL"')
            else:
                yield dev.write('TRIG:EDGE:SLOP {}'.format(slope))
                resp = yield dev.query('TRIG:EDGE:SLOP?')
        returnValue(resp)

    @setting(134, mode='s', returns=['s'])
    def trigger_sweep(self, c, mode=None):
        """Get or set the trigger mode

        Must be "AUTO", "TRIG" (normal), or "SING" (single)
        """
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.query('TRIG:SWE?')
        else:
            mode = mode.upper()
            if mode not in ['AUTO', 'TRIG', 'SING']:
                raise Exception('Mode must be "AUTO", "TRIG", or "SING".')
            else:
                yield dev.write('TRIG:SWE {}'.format(mode))
                resp = yield dev.query('TRIG:SWE?')
        returnValue(resp)

    @setting(150, side='s', returns=['s'])
    def horiz_refpoint(self, c, side=None):
        """Get or set the reference point for the horizontal position.

        Must be 'LEFT', 'CENT'er, or 'RIGH't.
        """
        dev = self.selectedDevice(c)
        if side is None:
            resp = yield dev.query('TIM:REF?')
        else:
            side = side.upper()
            if side not in ['LEFT', 'CENT', 'RIGH']:
                raise Exception('Mode must be "LEFT", "CENT", or "RIGH".')
            else:
                yield dev.write('TIM:REF {}'.format(side))
                resp = yield dev.query('TIM:REF?')
        returnValue(resp)

    @setting(151, position='v', returns=['v'])
    def horiz_position(self, c, position=None):
        """Get or set the horizontal trigger position.

        With respect to value from horiz_refpoint, in seconds.
        """
        dev = self.selectedDevice(c)
        if position is None:
            resp = yield dev.query('TIM:POS?')
        else:
            yield dev.write('TIM:POS {}'.format(position))
            resp = yield dev.query('TIM:POS?')
        position = float(resp)
        returnValue(position)

    @setting(152, scale='v', returns=['v'])
    def horiz_scale(self, c, scale=None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('TIM:SCAL?')
        else:
            scale = format(scale, 'E')
            yield dev.write('TIM:SCAL {}'.format(scale))
            resp = yield dev.query('TIM:SCAL?')
        scale = float(resp)
        returnValue(scale)
    
    # Data acquisition settings
    @setting(201, channel='i', start='i', stop='i',
             returns='*v[ns] {time axis} *v[mV] {scope trace}')
    def get_trace(self, c, channel, start=1, stop=10000):
        """Get a trace from the scope.
        OUTPUT - (array voltage in volts, array time in seconds)
        """
        # raise Exception('Doesnt work yet. Please fix lines defining
        # trace_volts and time.')
        # DATA ENCODINGS
        # RIB - signed, MSB first
        # RPB - unsigned, MSB first
        # SRI - signed, LSB first
        # SRP - unsigned, LSB first
        word_length = 2  # Hardcoding to set data transer word length to 2 bytes
        
        dev = self.selectedDevice(c)
        yield dev.write('WAV:SOUR CHAN{}'.format(channel))

        # Read data MSB first
        yield dev.write('WAV:BYT MSBF')
        # Set 2 bytes per point
        yield dev.write('WAV:FORM WORD')
        # Starting and stopping point
        # Transfer waveform preamble
        preamble = yield dev.query('WAV:PRE?')
        # Transfer waveform data
        p = dev._packet().write('WAV:DATA?').read_raw()
        result = yield p.send()
        binary = result['read_raw']
        binary = binary[:-1]
        # Parse waveform preamble
        preample_dict = _parsePreamble(preamble)
        # Parse binary
        trace = _parseBinaryData(binary, word_length=word_length)
        # Convert from binary to volts

        y_step = float(preample_dict['yStep'])
        origin = float(preample_dict['yOrigin'])
        trace_volts = (trace * y_step) + origin

        num_points = int(preample_dict['numPoints'])
        x_step = float(preample_dict['xStep'])
        first = float(preample_dict['xFirst'])
        time = numpy.linspace(first, first + (num_points-1) * x_step, num_points)

        returnValue((time*U.ns*1e9, trace_volts*U.V))


def _parsePreamble(preamble):
    preamble_vals = preamble.split(',')
    '''
    preamble_keys = [('byteFormat',True),
                    ('dataType',False),
                    ('numPoints',True),
                    ('count',False),
                    ('xStep',True),
                    ('xFirst',True),
                    ('xRef',False),
                    ('yStep',True),
                    ('yOrigin',True),
                    ('yRef',False),
                    ('coupling',False),
                    ('xRange',True),
                    ('xLeftDisplay',True),
                    ('yRange',True),
                    ('yCenterDisplay',True),
                    ('date',False),
                    ('time',False),
                    ('model',False),
                    ('acquisitionMode',False),
                    ('percentTimeBucketsComplete',False),
                    ('xUnits',True),
                    ('yUnits',True),
                    ('maxBW',False),
                    ('minBW',False)]
    '''
    preamble_keys = [('byteFormat', True),
                ('dataType', True),
                ('numPoints', True),
                ('count', True),
                ('xStep', True),
                ('xFirst', True),
                ('xRef', True),
                ('yStep', True),
                ('yOrigin', True),
                ('yRef', True),
                ('coupling', True),
                ('xRange', True),
                ('xLeftDisplay', True),
                ('yRange', True),
                ('yCenterDisplay', True),
                ('date', True),
                ('time', True),
                ('model', True),
                ('acquisitionMode', True),
                ('percentTimeBucketsComplete', True),
                ('xUnits', True),
                ('yUnits', True),
                ('maxBW', True),
                ('minBW', True)]
    preample_dict = {}
    for key, val in zip(preamble_keys, preamble_vals):
        if key[1]:
            preample_dict[key[0]] = val

    def unit_type(num):
        if num == '1':
            return 'V'
        elif num == '2':
            return 'ns'
        else:
            raise Exception('Units not time or voltage')
    preample_dict['xUnit'] = unit_type(preample_dict['xUnits'])
    preample_dict['yUnit'] = unit_type(preample_dict['yUnits'])
    return (preample_dict)


def _parseBinaryData(data, word_length):
    """Parse binary data packed as string of RIBinary
    """
    format_chars = {'1': 'b', '2': 'h', '4': 'f'}
    format_char = format_chars[str(word_length)]

    # Get rid of header
    # unpack binary data
    if word_length == 1:
        len_header = int(data[1])
        dat = data[(2+len_header):]
        dat = np.array(unpack(format_char*(len(dat)/word_length), dat))
    elif word_length == 2:
        len_header = int(data[1])
        dat = data[(2+len_header):]
        dat = dat[-calcsize('>' + format_char*(len(dat)/word_length)):]
        dat = np.array(unpack('>' + format_char*(len(dat)/word_length), dat))
    elif word_length == 4:
        len_header = int(data[1])
        dat = data[(2+len_header):]
        dat = dat[-calcsize('>' + format_char*(len(dat)/word_length)):]
        dat = np.array(unpack('>' + format_char*(len(dat)/word_length), dat))
    return dat

__server__ = AgilentDSO91304AServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
