from __future__ import absolute_import

import struct

import numpy as np
from twisted.internet.defer import inlineCallbacks, returnValue

import labrad.units as U
import oscilloscope.wrappers as wrappers


TRIGGER_MODES = [
        'COMM',
        'DEL',
        'EDGE',
        'GLIT',
        'PATT',
        'PWID',
        'RUNT',
        'SEQ',
        'SHOL',
        'STAT',
        'TIM',
        'TRAN',
        'TV',
        'WIND',
        'SBUS1',
        'SBUS2',
        'SBUS3',
        'SBUS4',
]

def _id(x):
    return x

PREAMBLE_UNITS = {1: U.V, 2: U.s, 4: U.A, 5: U.Unit('dB')}

PREAMBLE_KEYS = [
        ('byte_format', int),
        ('data_type', int),
        ('num_points', int),
        ('count', int),
        ('x_step', lambda x: float(x) * U.s),
        ('x_origin', lambda x: float(x) * U.s),
        ('x_reference', float),
        ('y_step', lambda x: float(x) * U.V),
        ('y_origin', lambda x: float(x) * U.V),
        ('y_reference', lambda x: float(x) * U.V),
        ('coupling', lambda x: {
            0:'AC',
            1:'DC',
            2:'DCFIFTY',
            3:'LFREJECT'}[int(x)]),
        ('x_display_range', lambda x: float(x) * U.s),
        ('x_display_origin', lambda x: float(x) * U.s),
        ('y_display_range', lambda x: float(x) * U.V),
        ('y_display_origin', lambda x: float(x) * U.V),
        ('date', _id),  # Convert to a real date
        ('time', _id),  # Convert to a real time
        ('frame_model', _id),
        ('acquisition_mode', int),  # Convert to string?
        ('completion', int),
        ('x_units', lambda x: PREAMBLE_UNITS[int(x)]),
        ('y_units', lambda x: PREAMBLE_UNITS[int(x)]),
        ('max_bandwidth_limit', lambda x: float(x) * U.Hz),
        ('min_bandwidth_limit', lambda x: float(x) * U.Hz),
]
# The preamble comes back from the scope as a comma separated string.
# The order of the keys here matches the order of the values in the comma
# separated string.

def not_implemented_channel_method(message):
    def func(self, ch, arg):
        raise NotImplementedError(message)
    return func


class DSO91304AWrapper(wrappers.OscilloscopeWrapper):
    """Wrapper for the Agilent DSO91304A.

    We mostly override VISA string functions from the parent class, but in some
    cases we have to write complete self-contained methods. This file should be
    viewed along side the parent class in order to understand what's going on.

    See programmer manual at:
        http://www.keysight.com/upload/cmc_upload/All/Infiniium_prog_guide.pdf
    """

    # CHANNEL

    channel_on = wrappers.channel_method(
            lambda x: {True: '1', False: '0'}[x],
            ':CHAN{:d}:DISP {}'.format,
            ':CHAN{:d}:DISP?'.format,
            lambda x: {'1': True, '0': False}[x])

    coupling = not_implemented_channel_method(
        "Coupling not configurable on this device, DC only.")

    invert = not_implemented_channel_method(
        "invert doesn't work for some reason")
    """
    invert = wrappers.channel_method(
            lambda x: {True: '1', False: '0'}[x],
            ':CHAN{:d}:INV {}'.format,
            ':CHAN{:d}:INV?'.format,
            lambda x: {'1': True, '0': False}[x])
    """

    def termination(self, ch, arg):
        if arg == 50 or arg is None:
            return 50
        else:
            raise ValueError("Termination can only be 50, not {}".format(
                    arg))

    vert_scale = wrappers.channel_method(
            lambda x: format(x['V'], 'E'),
            ':CHAN{:d}:SCAL {}V'.format,
            ':CHAN{:d}:SCAL?'.format,
            lambda x: float(x) * U.Value(1, 'V'))

    @inlineCallbacks
    def vert_position(self, channel, position=None):
        scale = yield self.vert_scale(channel)
        if position is not None:
            pos_V = -(position * scale)['V']
            yield self.write(':CHAN{:d}:OFFS {} V'.format(channel, pos_V))
        resp = yield self.query(':CHAN{:d}:OFFS?'.format(channel))
        returnValue(-float(resp) / scale['V'])

    horiz_scale = wrappers.global_method(
            lambda x: x['s'],
            ':TIM:SCAL {:E}'.format,
            ':TIM:SCAL?'.format,
            lambda x: float(x) * U.Value(1, 's'))

    @inlineCallbacks
    def horiz_position(self, position=None):
        horiz_scale = yield self.horiz_scale()
        if position is not None:
            pos = position * horiz_scale
            yield self.write(':TIM:POS {}'.format(-pos['s']))
        resp = yield self.query(':TIM:POS?')
        returnValue(-float(resp) * U.Unit('s') / horiz_scale)

    # TRIGGER

    trigger_source = wrappers.global_method(
            wrappers.filter_function(
                'EXT', 'LINE', 'CHAN1', 'CHAN2', 'CHAN3', 'CHAN4'),
            ':TRIG:EDGE:SOUR {}'.format,
            ':TRIG:EDGE:SOUR?'.format,
            lambda x: x)

    trigger_slope = wrappers.global_method(
            wrappers.filter_function('POS', 'NEG'),
            ':TRIG:EDGE:SLOP {}'.format,
            ':TRIG:EDGE:SLOP?'.format,
            lambda x: x)

    @inlineCallbacks
    def trigger_level(self, level):
        """Set and/or query the trigger level.

        This scope is a bit different from some others in that the trigger
        level is set for a particular channel. To keep the interface simple,
        we set/query the trigger level for whichever channel is presently
        set as the trigger source.
        """
        source = yield self.trigger_source()
        if level is not None:
            self.write(':TRIG:LEV {}, {}'.format(source, level[U.V]))
        level = yield self.query(':TRIG:LEV? {}'.format(source))
        returnValue(float(level)*U.V)

    trigger_mode = wrappers.global_method(
            wrappers.filter_function(TRIGGER_MODES),
            'TRIG:MODE {}'.format,
            'TRIG:MODE?'.format,
            lambda x: x)

    # ACQUISITION
    average_on_off = wrappers.global_method(
            lambda x: {True: 1, False: 0}[x],
            'ACQ:AVER {}'.format,
            'ACQ:AVER?'.format,
            lambda x: bool(int(x)))

    average_number = wrappers.global_method(
            lambda x: x,
            'ACQ:AVER:COUN {}'.format,
            'ACQ:AVER:COUN?'.format,
            lambda x: int(x))

    @inlineCallbacks
    def get_trace(self, channel):
        """Get a trace.

        Args:
            channel (int): Which channel to get.

        Returns: (ValueArray[s]): Time axis.
            (ValueArray[V]): Voltage axis.
        """
        word_length = 2

        channel_on = yield self.channel_on(channel)
        if not channel_on:
            raise RuntimeError('Cannot get trace from channel {} because it '
                               'is not on'.format(channel))

        yield self.write(':WAV:SOUR CHAN{}'.format(channel))
        yield self.write(':WAV:BYT MSBF')
        yield self.write(':WAV:FORM WORD')

        preamble_raw = yield self.query(':WAV:PRE?')
        preamble = parse_preamble(preamble_raw)

        yield self.write(':WAV:DATA?')
        wave_bin = yield self.read_raw()
        wave_raw = parse_binary_waveform(wave_bin, word_length=word_length)

        y_incriment = preamble['y_step']
        y_origin = preamble['y_origin']
        y_reference = preamble['y_reference']
        wave = ((wave_raw - y_reference[U.V]) * y_incriment) + y_origin

        x_incriment = preamble['x_step']
        x_origin = preamble['x_origin']
        num_points = preamble['num_points']
        time = np.linspace(
                x_origin[U.s],
                x_origin[U.s] + ((num_points-1) * x_incriment[U.s]),
                num_points) * U.s
        returnValue((time, wave))


def parse_preamble(preamble):
    """Parse the waveform preamble.

    Args:
        preamble (str): ASCII-encoded, comma-separated preamble.

    Returns:
        (dict): Mapping field names to their values.
    """
    results = {}
    fields = preamble.split(',')
    for (key, parser), val in zip(PREAMBLE_KEYS, fields):
        results[key] = parser(val)
    return results


def parse_binary_waveform(data, word_length):
    """Convert binary waveform dump to numpy array.

    Args:
        data (str): binary encoded data.
        word_length (int): Number of bytes per data point.

    Returns:
        (ndarray): voltage trace values. The units depend on the scope.
    """
    format_char = {1: 'B', 2: 'h'}[word_length]
    if data[0] != '#':
        raise ValueError("Invalid data. Expected '#' "
                         "at start, but got {}".format(data[0]))
    header_len = int(data[1])
    offset = 2 + header_len
    wave_len = int(data[2:offset])
    expected_len = 1 + 1 + header_len + wave_len + 1
    if len(data) != expected_len:
        raise ValueError("Data length {} but expected {}".format(
            expected_len, len(data)))
    wave_data = data[offset:offset + wave_len]
    num_words, r = divmod(wave_len, word_length)
    words = struct.unpack('>' + format_char * num_words, wave_data)
    return np.array(words)
