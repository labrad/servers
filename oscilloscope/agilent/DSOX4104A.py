from __future__ import absolute_import

import struct

import numpy as np
from twisted.internet.defer import inlineCallbacks, returnValue

import labrad.units as U
import oscilloscope.wrappers as wrappers


class DSOX4104AWrapper(wrappers.OscilloscopeWrapper):
    """Wrapper for the Agilent DSO-X 4104A

    We mostly override VISA string functions from the parent class, but in some
    cases we have to write complete self-contained methods. This file should be
    viewed along side the parent class in order to understand what's going on.

    See programmer manual at:
        http://www.keysight.com/upload/cmc_upload/All/4000_series_prog_guide.pdf?&cc=US&lc=eng
    """

    # CHANNEL

    channel_on = wrappers.channel_method(
            lambda x: {True: '1', False: '0'}[x],
            ':CHAN{:d}:DISP {}'.format,
            ':CHAN{:d}:DISP?'.format,
            lambda x: {'1': True, '0': False}[x])

    coupling = wrappers.channel_method(
            lambda x: x,
            ':CHAN{:d}:COUP {}'.format,
            ':CHAN{:d}:COUP?'.format,
            lambda x: x)

    invert = wrappers.channel_method(
            lambda x: {True: '1', False: '0'}[x],
            ':CHAN{:d}:INV {}'.format,
            ':CHAN{:d}:INV?'.format,
            lambda x: {'1': True, '0': False}[x])

    termination = wrappers.channel_method(
            lambda x: {50:'FIFT', 1000000:'ONEM'}[x],
            ':CHAN{:d}:IMP {}'.format,
            ':CHAN{:d}:IMP?'.format,
            lambda x: {'FIFT': 50, 'ONEM': 1000000}[x])

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
            ':TIM:SCAL {}'.format,
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

    trigger_level = wrappers.global_method(
            lambda x: x['V'],
            ':TRIG:EDGE:LEV {}'.format,
            ':TRIG:EDGE:LEV?'.format,
            lambda x: float(x) * U.Value(1, 'V'))

    @inlineCallbacks
    def get_trace(self, channel):
        """Get a trace.

        Args:
            channel (int): Which channel to get.

        Returns:
            (ValueArray[s]): Time axis.
            (ValueArray[V]): Voltage axis.
        """
        word_length = 2
        yield self.write(':WAV:SOUR CHAN{}'.format(channel))
        yield self.write(':WAV:MSBF')
        yield self.write(':SING')
        preamble_raw = yield self.query(':WAV:PRE?')
        preamble = parse_preamble(preamble_raw)
        yield self.write(':WAV:FORM WORD')
        yield self.write(':WAV:DATA?')
        wave_bin = yield self.read_raw()
        wave_raw = parse_binary_waveform(wave_bin, word_length=word_length)

        y_incriment = preamble['y_incriment']
        y_origin = preamble['y_origin']
        y_reference = preamble['y_reference']
        wave_volts = ((wave_raw - y_reference) * y_incriment) + y_origin

        x_incriment = preamble['x_incriment']
        x_origin = preamble['x_origin']
        num_points = preamble['num_points']
        time_s = np.linspace(
                x_origin,
                x_origin + (num_points-1) * x_incriment,
                num_points)
        returnValue((time_s * U.Unit('s'), wave_volts * U.Unit('V')))
 

def parse_preamble(preamble):
    """Parse the waveform preamble.

    Args:
        preamble (str): ASCII encoded preamble.

    Returns:
        (dict): Mapping field names to their values.
    """
    fields = preamble.split(',')
    num_points = int(fields[2])
    x_incriment = float(fields[4])
    x_origin = float(fields[5])
    x_reference = int(fields[6])
    y_incriment = float(fields[7])
    y_origin = float(fields[8])
    y_reference = int(fields[9])
    return {'num_points': num_points,
            'x_incriment': x_incriment,
            'x_origin': x_origin,
            'x_reference': x_reference,
            'y_incriment': y_incriment,
            'y_origin': y_origin,
            'y_reference': y_reference}


def parse_binary_waveform(data, word_length):
    """Convert binary waveform dump to numpy array.

    Args:
        data (str): binary encoded data.
        word_length (int): Number of bytes per data point.

    Returns:
        (ndarray): voltage trace values. The units depend on the scope.
    """
    format_char = {1: 'B', 2: 'H'}[word_length]
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

