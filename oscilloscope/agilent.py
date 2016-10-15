"""
Wrappers for Agilent oscilloscopes.

"""


from __future__ import absolute_import

import struct

import numpy as np
from twisted.internet.defer import inlineCallbacks, returnValue

import labrad.units as U
import oscilloscope.wrappers as wrappers


class AgilentDSOX4104AWrapper(wrappers.OscilloscopeWrapper):
    """Wrapper for the Agilent DSO-X 4104A

    We mostly override VISA string functions from the parent class, but in some
    cases we have to write complete self-contained methods. This file should be
    viewed along side the parent class in order to understand what's going on.

    See programmer manual at:
        http://www.keysight.com/upload/cmc_upload/All/4000_series_prog_guide.pdf?&cc=US&lc=eng
    """

    # CHANNEL

    channel_on_off_write = ':CHAN{0}:DISP {1}'.format
    channel_on_off_query = ':CHAN{0}:DISP?'.format
    @staticmethod
    def channel_on_off_parse(s):
        return {'0':'OFF', '1': 'ON'}[s]

    coupling_write = ':CHAN{0}:COUP {1}'.format
    coupling_query = ':CHAN{0}:COUP?'.format
    coupling_parse = str

    channel_invert_write = ':CHAN{0}:INV {1}'.format
    channel_invert_query = ':CHAN{0}:INV?'.format
    channel_invert_parse = int

    IMPEDANCES = {50:'FIFT', 1000000:'ONEM'}
    def termination_write(self, ch, imp):
        return ':CHAN{0}:IMP {1}'.format(ch, self.IMPEDANCES[imp])
    def termination_query(self, ch):
        return ':CHAN{0}:IMP?'.format(ch)
    def termination_parse(self, s):
        return {v: k for k, v in self.IMPEDANCES.items()}[s]

    VERT_SCALE_UNIT = U.Unit('V')  # Device always returns Volts.
    vert_scale_write = ':CHAN{0}:SCAL {1}V'.format
    vert_scale_query = ':CHAN{0}:SCAL?'.format
    @classmethod
    def vert_scale_parse(cls, st):
        return float(st) * cls.VERT_SCALE_UNIT

    @inlineCallbacks
    def vert_position(self, channel, position=None):
        scale = yield self.vert_scale(channel)
        if position is not None:
            pos_V = -(position * scale)['V']
            yield self.write(':CHAN{0}:OFFS {1} V'.format(channel, pos_V))
        resp = yield self.query(':CHAN{0}:OFFS?'.format(channel))
        returnValue(-float(resp) / scale['V'])

    HORIZ_SCALE_UNIT = U.Unit('s')
    horiz_scale_write = ':TIM:SCAL {0}'.format
    horiz_scale_query = ':TIM:SCAL?'.format
    def horiz_scale_parse(self, x):
        return float(x) * self.HORIZ_SCALE_UNIT 

    @inlineCallbacks
    def horiz_position(self, position=None):
        horiz_scale = yield self.horiz_scale()
        if position is not None:
            pos = position * horiz_scale
            yield self.write(':TIM:POS {}'.format(-pos['s']))
        resp = yield self.query(':TIM:POS?')
        returnValue(-float(resp) * U.Unit('s') / horiz_scale)
        
    # TRIGGER

    TRIGGER_SOURCES = ['EXT', 'LINE', 'CHAN1', 'CHAN2', 'CHAN3', 'CHAN4']
    trigger_source_write = ':TRIG:EDGE:SOUR {0}'.format
    trigger_source_query = ':TRIG:EDGE:SOUR?'.format
    @staticmethod
    def trigger_source_parse(x):
        return x

    TRIGGER_SLOPES = ['POS', 'NEG']
    trigger_slope_write = ':TRIG:EDGE:SLOP {}'.format
    trigger_slope_query = ':TRIG:EDGE:SLOP?'.format
    @staticmethod
    def trigger_slope_parse(x):
        return x

    TRIGGER_LEVEL_UNIT = U.Unit('V')
    @classmethod
    def trigger_level_write(cls, level):
        return ':TRIG:EDGE:LEV {}'.format(level[cls.TRIGGER_LEVEL_UNIT])
    @staticmethod
    def trigger_level_query():
        return ':TRIG:EDGE:LEV?'
    @classmethod
    def trigger_level_parse(cls, level):
        return float(level) * cls.TRIGGER_LEVEL_UNIT

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

