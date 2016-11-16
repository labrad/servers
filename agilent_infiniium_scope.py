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
version = 0.3.0
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
import struct
import numpy as np
import time

COUPLINGS = ['AC', 'DC', 'GND']
TRIG_CHANNELS = ['AUX', 'CH1', 'CH2', 'CH3', 'CH4', 'LINE']
VERT_DIVISIONS = 8.0
HORZ_DIVISIONS = 10.0
SCALES = []
MAX_MISSED_TRIGGERS = 20
QUERY_PERIOD = 0.2
PREAMBLE_KEYS = [
    ('byteFormat', True),
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
    ('minBW', True)
]


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

    @setting(112, channel='i', scale='v[V]', returns=['v[V]'])
    def scale(self, c, channel, scale=None):
        """Get or set the vertical scale of a channel in voltage per division.
        """
        _check_channel(channel)
        dev = self.selectedDevice(c)
        if scale is not None:
            yield dev.write('CHAN{}:SCAL {:E}'.format(channel, scale['V']))
        resp = yield dev.query('CHAN{}:SCAL?'.format(channel))
        scale = float(resp) * U.V
        returnValue(scale)

    @setting(114, channel='i', state=['s', 'i'], returns='s')
    def channelOnOff(self, c, channel, state=None):
        """Turn on or off a scope channel display.

        State must be in [0,1,'ON','OFF'].
        Channel must be int.
        If state is not specified, will return state of channel.
        """
        _check_channel(channel)
        dev = self.selectedDevice(c)
        if state is not None:
            if isinstance(state, str):
                state = state.upper()
            if state not in [0, 1, 'ON', 'OFF']:
                raise Exception('state must be 0, 1, "ON", or "OFF". '
                                'Got {}'.format(state))
            yield dev.write('CHAN{}:DISP {}'.format(channel, state))
        resp = yield dev.query('CHAN{}:DISP?'.format(channel))
        returnValue(resp)

    @setting(117, channel='i', position='v[V]', returns=['v[V]'])
    def position(self, c, channel, position=None):
        """Get or set the voltage at the center of the screen
        """
        _check_channel(channel)
        dev = self.selectedDevice(c)
        if position is not None:
            yield dev.write('CHAN{}:OFFS {}'.format(channel, position['V']))
        resp = yield dev.query('CHAN{}:OFFS?'.format(channel))
        position = float(resp) * U.V
        returnValue(position)

    @setting(118, mode=['s', 'i', 'b'], returns=['s'])
    def averagemode(self, c, mode=None):
        """Get or set acquisition mode
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            if isinstance(mode, str):
                mode = mode.upper()
                mode = {'ON': 1, 'OFF': 0}[mode]
            elif isinstance(mode, bool):
                mode = int(mode)
            yield dev.write('ACQ:AVER {}'.format(mode))
        resp = yield dev.query('ACQ:AVER?')
        returnValue(resp)

    @setting(119, navg='i', returns=['i'])
    def numavg(self, c, navg=None):
        """Get or set number of averages
        """
        dev = self.selectedDevice(c)
        if navg is not None:
            yield dev.write('ACQ:COUN {}'.format(navg))
        resp = yield dev.query('ACQ:COUN?')
        navg_out = int(resp)
        returnValue(navg_out)


    @setting(130, channel=['s', 'i'], returns='v{ch}')
    def trigger_channel(self, c, channel=None):
        """Get or set the trigger source edge mode triggering.

        Channel must be one of 0 (AUX), 1, 2, 3, 4, or 5 (LINE).
        """
        dev = self.selectedDevice(c)
        if channel is not None:
            _check_channel(channel, accept_channels=[0, 1, 2, 3, 4, 5])
            if channel == 0:
                channel = 'AUX'
            elif channel == 5:
                channel = 'LINE'
            elif isinstance(channel, int):
                channel = 'CHAN{}'.format(channel)
            yield dev.write(':TRIG:EDGE:SOUR {}'.format(channel))
        resp = yield dev.query(':TRIG:EDGE:SOUR?')
        if resp == 'AUX':
            ch = 0
        elif resp == 'LINE':
            ch = 5
        else:
            ch = np.int(resp[-1])
        returnValue(ch)

    @setting(131, channel='i', level='v[V]', returns='v[V] {level}')
    def trigger_at(self, c, channel, level=0 * U.V):
        """Get or set the trigger source and voltage for edge mode triggering.

        Channel must be one of 0 (AUX), 1, 2, 3, 4, or 5 (LINE).
        If trigger source is 5 (LINE) the level will be ignored
        """
        _check_channel(channel, accept_channels=[0, 1, 2, 3, 4, 5])
        dev = self.selectedDevice(c)
        if channel == 0:
            channel = 'AUX'
        elif channel == 5:
            channel = 'LINE'
        elif isinstance(channel, int):
            channel = 'CHAN{}'.format(channel)
        yield dev.write(':TRIG:EDGE:SOUR {}'.format(channel))
        if channel == 'LINE':
            # Cannot set trigger level when triggering off line input.
            # See http://www.keysight.com/upload/cmc_upload/All/9000_series_prog_ref.pdf#page=914
            level = 0.0 * U.V
        else:
            # Set trigger level.
            print 'channel: {}'.format(channel)
            yield dev.write(':TRIG:LEV {}, {}'.format(channel, level['V']))
            resp = yield dev.query(':TRIG:LEV? {}'.format(channel))
            level = float(resp) * U.V
        resp2 = yield dev.query(':TRIG:EDGE:SOUR?')
        print 'Trigger on {} at {}'.format(resp2, level)
        returnValue(level)

    @setting(132, slope='s', returns=['s'])
    def trigger_mode(self, c, slope=None):
        """Change trigger mode. Use 'EDGE' for edge triggering.

        Must be one of 'COMM', 'DEL', 'EDGE', 'GLIT', 'PATT', 'PWID', 'RUNT',
        'SEQ', 'SHOL', 'STAT', 'TIM', 'TRAN', 'TV', 'WIND', 'SBUS1', 'SBUS2',
        'SBUS3', 'SBUS4'.
        """
        dev = self.selectedDevice(c)
        if slope is not None:
            slope = slope.upper()
            if slope not in ['COMM', 'DEL', 'EDGE', 'GLIT', 'PATT', 'PWID',
                             'RUNT', 'SEQ', 'SHOL', 'STAT', 'TIM', 'TRAN',
                             'TV', 'WIND', 'SBUS1', 'SBUS2', 'SBUS3', 'SBUS4']:
                raise Exception('Slope must be valid type, '
                                'not {}'.format(slope))
            yield dev.write('TRIG:MODE {}'.format(slope))
        resp = yield dev.query('TRIG:MODE?')
        returnValue(resp)

    @setting(133, slope='s', returns=['s'])
    def trigger_edge_slope(self, c, slope=None):
        """Change trigger edge slope.

        Must be 'POS,' 'NEG', or 'EITH'er
        """
        dev = self.selectedDevice(c)
        if slope is not None:
            slope = slope.upper()
            if slope not in ['POS', 'NEG', 'EITH']:
                raise Exception('Slope must be "POS" or "NEG" or "EITH". '
                                'Got {}'.format(slope))
            yield dev.write(':TRIG:EDGE:SLOP {}'.format(slope))
        resp = yield dev.query(':TRIG:EDGE:SLOP?')
        returnValue(resp)

    @setting(134, mode='s', returns=['s'])
    def trigger_sweep(self, c, mode=None):
        """Get or set the trigger mode

        Must be "AUTO", "TRIG" (normal), or "SING" (single)
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            mode = mode.upper()
            if mode not in ['AUTO', 'TRIG', 'SING']:
                raise Exception('Mode must be "AUTO", "TRIG", or "SING". '
                                'Got {}'.format(mode))
            yield dev.write('TRIG:SWE {}'.format(mode))
        resp = yield dev.query('TRIG:SWE?')
        returnValue(resp)

    @setting(135, filter='s', returns=['s'])
    def response_filter(self, c, filter=None):
        """Change trigger mode. 'FLAT' is default, 'GAUS' for pulse.

        """
        dev = self.selectedDevice(c)
        if filter is not None:
            filter = filter.upper()
            filter_types = ['GAUS', 'FLAT', 'GAUSs']
            if filter not in filter_types:
                raise Exception('Slope must be valid type ({}), '
                                'not {}'.format(filter_types, filter))
            yield dev.write(':ACQ:RESP {}'.format(filter))
        resp = yield dev.query(':ACQ:RESP?')
        returnValue(resp)

    @setting(150, side='s', returns=['s'])
    def horiz_refpoint(self, c, side=None):
        """Get or set the reference point for the horizontal position.

        Must be 'LEFT', 'CENT', or 'RIGH'.
        """
        dev = self.selectedDevice(c)
        if side is not None:
            side = side.upper()
            if side not in ['LEFT', 'CENT', 'RIGH']:
                raise Exception('Mode must be "LEFT", "CENT", or "RIGH". '
                                'Got {}'.format(side))
            yield dev.write('TIM:REF {}'.format(side))
        resp = yield dev.query('TIM:REF?')
        returnValue(resp)

    @setting(151, position='v', returns=['v'])
    def horiz_position(self, c, position=None):
        """Get or set the horizontal trigger position.

        With respect to value from horiz_refpoint, in seconds.
        """
        dev = self.selectedDevice(c)
        if position is not None:
            yield dev.write('TIM:POS {}'.format(position))
        resp = yield dev.query('TIM:POS?')
        position = float(resp)
        returnValue(position)

    @setting(152, scale='v', returns=['v'])
    def horiz_scale(self, c, scale=None):
        """Get or set the horizontal scale
        """
        dev = self.selectedDevice(c)
        if scale is not None:
            yield dev.write('TIM:SCAL {:E}'.format(scale))
        resp = yield dev.query('TIM:SCAL?')
        scale = float(resp)
        returnValue(scale)

    @setting(160, rate='v[Hz]', returns=['v[Hz]'])
    def sample_rate(self, c, rate=None):
        """Get or set the sample rate
        """
        dev = self.selectedDevice(c)
        if rate is not None:
            rate = rate['Hz']
            yield dev.write(':ACQ:SRAT:ANAL {}'.format(rate))
        resp = yield dev.query(':ACQ:SRAT:ANAL?')
        rate = float(resp) * U.Hz
        returnValue(rate)

    @setting(161, mode=['s', 'i', 'b'], returns=['s'])
    def external_time_ref(self, c, mode=None):
        """Get or set the external 10 MHz reference clock

        1 for external, 0 for internal reference clock.
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            if isinstance(mode, str):
                mode = mode.upper()
                mode = {'ON': 1, 'OFF': 0}[mode]
            elif isinstance(mode, bool):
                mode = int(mode)
            yield dev.write(':TIM:REFC {}'.format(mode))
        resp = yield dev.query('TIM:REFC?')
        returnValue(resp)

    @setting(162, mode=['s', 'i', 'b'], returns=['s'])
    def waveform_interpolation(self, c, mode=None):
        """Get or set waveform interpolation (on/off).

        Off is recommended
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            if isinstance(mode, str):
                mode = mode.upper()
                mode = {'ON': 1, 'OFF': 0}[mode]
            elif isinstance(mode, bool):
                mode = int(mode)
            yield dev.write(':ACQ:INT {}'.format(mode))
        resp = yield dev.query('ACQ:INT?')
        returnValue(resp)

    @setting(163, mode=['s', 'i', 'b'], returns=['s'])
    def waveform_streaming(self, c, mode=None):
        """Get or set waveform streaming (on/off).

        Off limits data transfers to (1e9 - 1) bytes.  Note:  This setting
        changes the waveform data parsing format.  Off definitely works as-is;
        On is not yet supported.
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            if isinstance(mode, str):
                mode = mode.upper()
                mode = {'ON': 1, 'OFF': 0}[mode]
            elif isinstance(mode, bool):
                mode = int(mode)
            yield dev.write(':ACQ:INT {}'.format(mode))
        resp = yield dev.query('ACQ:INT?')
        returnValue(resp)


    @setting(164, returns=[])
    def start_averaging(self, c):
        """Restart the waveform count in average mode.

        Clears buffers and restarts averages
        """
        dev = self.selectedDevice(c)
        yield dev.query('*CLS;*OPC?')
        yield dev.write(':SING')

    @setting(165, returns=['b'])
    def check_for_trigger(self, c):
        """Query device until trigger is received or MAX_MISSED_TRIGGERS.

        Queries the device to see if it has received a trigger.  Note, this
        status byte only resets when clear_buffers() is called or you read the
        status as True.  It is important to clear_buffers right before starting
        the acquisition with :SING otherwise the status bytes may indicate a
        received trigger and/or completed averaging with a stale status.
        """
        dev = self.selectedDevice(c)
        triggered = False
        count = 0
        while not triggered:
            if count > MAX_MISSED_TRIGGERS:
                raise Exception('Error, trigger not received after {} attempts.'
                                'Please check trigger signal and trigger'
                                ' settings.'.format(MAX_MISSED_TRIGGERS))
            else:
                resp = yield dev.query(':TER?')
                triggered = int(resp)
                count += 1
                time.sleep(QUERY_PERIOD)
        returnValue(bool(triggered))

    @setting(166, returns=['i'])
    def wait_for_waveform_averages(self, c):
        """Query device until trigger is received or MAX_MISSED_TRIGGERS.

        Queries the device to see if it has received a trigger.  Note, this
        status byte only resets when clear_buffers() is called or you read the
        status as True.  It is important to clear_buffers right before starting
        the acquisition with :SING otherwise the status bytes may indicate a
        received trigger and/or completed averaging with a stale status.

        Returns the waveform count.
        """
        dev = self.selectedDevice(c)
        status = 0
        count = 0
        while status != 1:
            resp1 = yield dev.query(':ADER?')
            status = int(resp1)
            resp2 = yield dev.query(':WAV:COUN?')
            waveform_count = resp2
            time.sleep(QUERY_PERIOD)
            print 'Waveform count: {};' \
                  ' Averaging complete: {} {}'.format(waveform_count, status,
                                                      count)
            count += 1
        waveform_count = int(resp2)
        dev.query(':STOP;*OPC?')
        returnValue(waveform_count)

    @setting(167, channel='i', probe='i', returns='v{probe}')
    def probe(self, c, channel, probe=None):
        """Get or set the channel probe.

        This should be 1 unless scope probes are in use.  Expressed as a ratio.
        This could be modified to support DECible in addition to RATio.
        http://www.keysight.com/upload/cmc_upload/All/9000_series_prog_ref.pdf?&cc=US&lc=eng#page=217
        """
        _check_channel(channel, accept_channels=[1, 2, 3, 4])
        dev = self.selectedDevice(c)
        if probe is not None:
            yield dev.write(':CHAN{}:PROB {}, RAT'.format(channel, probe))
        resp = yield dev.query(':CHAN{}:PROB?'.format(channel))
        probe = float(resp.split(',')[0])
        returnValue(probe)

    @setting(168, bw='v[Hz]', returns=['v[Hz]'])
    def bandwidth(self, c, bw=None):
        """Get or set the sample rate
        """
        dev = self.selectedDevice(c)
        if bw is not None:
            bw = bw['Hz']
            yield dev.write(':ACQ:BAND {}'.format(bw))
        resp = yield dev.query(':ACQ:BAND?')
        rate = float(resp) * U.Hz
        rate = rate['GHz'] * U.GHz
        returnValue(rate)

    @setting(169, returns=[])
    def stop(self, c):
        dev = self.selectedDevice(c)
        yield dev.query(':STOP;*OPC?')

    # Data acquisition settings
    @setting(201, channel='i', start='i', stop='i',
             returns='*v[ns] {time axis} *v[mV] {scope trace}')
    def get_trace(self, c, channel, start=1, stop=10000):
        """Get a trace from the scope.

        OUTPUT - (array voltage in volts, array time in seconds)
        """
        # DATA ENCODINGS
        # RIB - signed, MSB first
        # RPB - unsigned, MSB first
        # SRI - signed, LSB first
        # SRP - unsigned, LSB first
        word_length = 2  # Hardcoding to set data transer word length to 2 bytes
        _check_channel(channel)
        dev = self.selectedDevice(c)
        channel_on = yield dev.query(':CHAN{}:DISP?'.format(channel))
        if not bool(int(channel_on)):
            raise Exception('channel {} is not on.'.format(channel))

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
        # Parse waveform preamble
        preamble_dict = _parsePreamble(preamble)
        # Parse binary
        trace = _parseBinaryData(binary, word_length=word_length)
        # Convert from binary to volts

        y_step = float(preamble_dict['yStep'])
        origin = float(preamble_dict['yOrigin'])
        trace_volts = (trace * y_step) + origin

        num_points = int(preamble_dict['numPoints'])
        x_step = float(preamble_dict['xStep'])
        first = float(preamble_dict['xFirst'])
        time_s = np.linspace(first, first + (num_points-1) * x_step, num_points)

        time_ns = time_s * 1e9
        returnValue((time_ns * U.ns, trace_volts * U.V))


def _check_channel(channel, accept_channels=[1, 2, 3, 4]):
    if channel not in accept_channels:
        trigger_channel_message = ''
        if 0 in accept_channels or 5 in accept_channels:
            trigger_channel_message = '; Note: 0 is AUX, 5 is LINE'
        raise Exception('channel must be int({}), requested {} ({})'
                        '{}'.format(accept_channels, channel, type(channel),
                                    trigger_channel_message))


def _parsePreamble(preamble):
    preamble_vals = preamble.split(',')
    preamble_dict = {}
    for (key, included), val in zip(PREAMBLE_KEYS, preamble_vals):
        if included:
            preamble_dict[key] = val

    def unit_type(num):
        if num == '1':
            return 'V'
        elif num == '2':
            return 'ns'
        else:
            raise Exception('Units not time or voltage')
    preamble_dict['xUnit'] = unit_type(preamble_dict['xUnits'])
    preamble_dict['yUnit'] = unit_type(preamble_dict['yUnits'])
    return preamble_dict


def _parseBinaryData(data, word_length):
    """Parse binary data packed as string of RIBinary

    Data format discussed here:
    http://www.keysight.com/upload/cmc_upload/All/9000_series_prog_ref.pdf?&cc=US&lc=eng#page=1091
    """
    format_chars = {1: 'b', 2: 'h', 4: 'f'}
    format_char = format_chars[word_length]

    if data[0] != '#':
        raise Exception("Invalid wave data. Expected '#' "
                        "at start but got {}".format(data[0]))
    len_header = int(data[1])
    wave_offset = 2 + len_header
    len_wave = int(data[2:wave_offset])
    expected_len = 1 + 1 + len_header + len_wave + 1
    if len(data) != expected_len:
        raise Exception("Invalid wave data. Expected {} bytes "
                        "but got {}.".format(expected_len, len(data)))
    wave_data = data[wave_offset:wave_offset + len_wave]
    num_words = len_wave // word_length
    words = struct.unpack('>' + format_char * num_words, wave_data)
    return np.array(words)

__server__ = AgilentDSO91304AServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
