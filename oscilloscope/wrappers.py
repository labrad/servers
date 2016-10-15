from __future__ import absolute_import

import numpy
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T
from labrad.gpib import GPIBDeviceWrapper


def require_is_in(obj, collection):
    if obj not in collection:
        raise ValueError("%s not in %s"%(obj, collection))


class NotImplementedAttribute(object):
    """An attribute which has not been implemented."""

    def __init__(self, label):
        self.label = label

    def __get__(self, inst, cls):
        """Raise AttributeError because this attribute should be overridden"""
        raise AttributeError("Attribute {} of class {} not implemented".format(
            self.label,
            cls))


class OscilloscopeWrapper(GPIBDeviceWrapper):
    """Base class for oscilloscope wrappers

    We provide iterpolatable strings which can be treated as functions to
    generate VISA commands. For example, consider the string
        'CH{0}:COUP {1}'.
    This string has a .format method, which is a function that takes two
    arguments. When you call that function with arguments 0 and "ON", the
    result is
        'CH0:COUP ON'
    which is the VISA command that turns on channel 0.
    """

    # CHANNEL

    # input

    CHANNEL_STATES = ['ON', 'OFF']
    channel_on_off_write = NotImplementedAttribute('channel_on_off_write')
    channel_on_off_query = NotImplementedAttribute('channel_on_off_query')
    channel_on_off_parse = NotImplementedAttribute('channel_on_off_parse')

    COUPLINGS = ['AC', 'DC']
    coupling_write = ':CH{0}:COUP {1}'.format
    coupling_query = ':CH{0}:COUP?'.format
    coupling_parse = str

    channel_invert_write = NotImplementedAttribute('channel_invert_write')
    channel_invert_query = NotImplementedAttribute('channel_invert_query')
    channel_invert_parse = NotImplementedAttribute('channel_invert_parse')

    IMPEDANCES = NotImplementedAttribute('IMPEDANCES')
    termination_write = NotImplementedAttribute('termination_write')
    termination_query = NotImplementedAttribute('termination_query')
    termination_parse = NotImplementedAttribute('termination_parse') 

    PROBE_FACTORS = NotImplementedAttribute('PROBE_FACTORS')
    probe_factor_write = NotImplementedAttribute('probe_factor_write')
    probe_factor_query = NotImplementedAttribute('probe_factor_query')
    probe_factor_parse = NotImplementedAttribute('probe_factor_parse')

    # scale, position, etc.

    VERT_SCALE_UNIT = NotImplementedAttribute('VERT_SCALE_UNIT')
    vert_scale_write = ':CH{0}:SCA {1}'.format
    vert_scale_query = ':CH{0}:SCA?'.format
    @classmethod
    def vert_scale_parse(cls, s):
        return float(s) * cls.VERT_SCALE_UNIT

    vert_position_write = NotImplementedAttribute('vert_position_write')
    vert_position_query = NotImplementedAttribute('vert_position_query')
    vert_position_parse = NotImplementedAttribute('vert_position_parse')

    HORIZ_SCALE_UNIT = NotImplementedAttribute('HORIZ_SCALE_UNIT')
    horiz_scale_write = NotImplementedAttribute('horiz_scale_write')
    horiz_scale_query = NotImplementedAttribute('horiz_scale_query')
    horiz_scale_parse = NotImplementedAttribute('horiz_scale_parse')

    HORIZ_POSITION_UNIT = NotImplementedAttribute('HORIZ_POSITION_UNIT')
    horiz_position_write = NotImplementedAttribute('horiz_position_write')
    horiz_position_query = NotImplementedAttribute('horiz_position_query')
    horiz_position_parse = NotImplementedAttribute('horize_position_parse') 

    # TRIGGER

    TRIGGER_SOURCES = NotImplementedAttribute('TRIGGER_SOURCES')
    trigger_source_write = NotImplementedAttribute('trigger_source_write')
    trigger_source_query = NotImplementedAttribute('trigger_source_query')
    trigger_source_parse = NotImplementedAttribute('trigger_source_parse')

    TRIGGER_SLOPES = NotImplementedAttribute('TRIGGER_SLOPES')
    trigger_slope_write = NotImplementedAttribute('trigger_slope_write')
    trigger_slope_query = NotImplementedAttribute('trigger_slope_query')
    trigger_slope_parse = NotImplementedAttribute('trigger_slope_parse')

    TRIGGER_LEVEL_UNIT = NotImplementedAttribute('TRIGGER_LEVEL_UNIT')
    trigger_level_write = NotImplementedAttribute('trigger_level_write')
    trigger_level_query = NotImplementedAttribute('trigger_level_query')
    trigger_level_parse = NotImplementedAttribute('trigger_level_parse')

    TRIGGER_MODES = ["AUTO", "NORM"]
    trigger_mode_write = ':TRIG:MOD {0}'.format
    trigger_mode_query = ':TIRG:MOD?'.format
    trigger_mode_parse = str  # XXX is this correct?


    # Functions which actually communicate with the hardware

    @inlineCallbacks
    def reset(self):
        """Reset the oscilloscope to factory settings."""
        yield self.write('*RST')

    @inlineCallbacks
    def clear_buffers(self):
        """Clear all device status bytes"""
        yield self.write('*CLS')

    # CHANNEL

    @inlineCallbacks
    def channel_on_off(self, channel, state=None):
        """Get or set channel on/off.

        Args:
            channel - int: The channel to get or set.
            state - str: 'ON' or 'OFF'.

        Returns:
            String giving the state of the channel.
        """
        if state is not None:
            require_is_in(state, self.CHANNEL_STATES)
            yield self.write(self.channel_on_off_write(channel, state))
        resp = yield self.query(self.channel_on_off_query(channel))
        returnValue(self.channel_on_off_parse(resp))

    @inlineCallbacks
    def coupling(self, channel, coupling=None):
        """Get or set the coupling for a channel.

        Args:
            channel: The channel to get or set. Typically this is a number from
                1 to 4.
            coupling: The coupling for this channel. If None (the default) then
                the current coupling is queried and returned. Otherwise the
                coupling is set and then queried and the result is returned.
        """
        if coupling is not None:
            require_is_in(coupling, self.COUPLINGS)
            yield self.write(self.coupling_write(channel, coupling))
        resp = yield self.query(self.coupling_query(channel))
        returnValue(self.coupling_parse(resp))

    @inlineCallbacks
    def invert(self, channel, invert):
        if invert is not None:
            yield self.write(self.channel_invert_write(channel, invert))
        resp = yield self.query(self.channel_invert_query(channel, invert))
        returnValue(self.channel_invert_parse(resp))

    @inlineCallbacks
    def termination(self, channel, impedance=None):
        """Get or set the channel's termination impedance.

        Args:
            Channel: The channel on which we get or set the impedance.
            impedance: The impedance to set. If None (the default) we just query
                the current impedance. Otherwise we set the impedance to the
                given value.

        Returns:
            The termination impedance of the channel.
        """
        if impedance is not None:
            require_is_in(impedance, self.IMPEDANCES.keys())
            yield self.write(self.termination_write(channel, impedance))
        resp = yield self.query(self.termination_query(channel))
        returnValue(self.termination_parse(resp))

    # VERTICAL 

    @inlineCallbacks
    def vert_scale(self, channel, scale=None):
        """Get or set the verical scale of a channel.

        Args:
            channel - int: The channel to get or set.
            scale - Value[V]: The vertical scale for the channel. If None (the
                default) we query the current scale. Otherwise we set the scale
                and then query it.

        Returns:
            Vertical scale in Voltage units.
        """
        if scale is not None:
            scale_str = format(scale[self.VERT_SCALE_UNIT], 'E')
            yield self.write(self.vert_scale_write(channel, scale_str))
        resp = yield self.query(self.vert_scale_query(channel))
        returnValue(self.vert_scale_parse(resp))

    @inlineCallbacks
    def vert_position(self, channel, position=None):
        """Get or set the channel vertical position.

        Args:
            channel (int): The channel to get or set.
            position (float): The vertical position to set for the channel. If
                None (the default) we just query the current position.

        Returns:
            (float): The vertical position in units of divisions.
        """
        if position is not None:
            yield self.write(self.vert_position_write(channel, pos))
        resp = yield dev.query(self.vert_position_query(channel))
        returnValue(self.parse_vert_position(resp))

    # HORIZONTAL

    @inlineCallbacks
    def horiz_scale(self, scale=None):
        """Get or set the horizontal scale of a channel.

        Args:
            channel: The channel to get or set.
            scale value[s]: The horizontal scale for the channel. If None
                (the default) we query the current scale. Otherwise we set the
                scale and then query it.

        Returns:
            Horizontal scale in dimensions of time.
        """
        if scale is not None:
            scale = scale[self.HORIZ_SCALE_UNIT]
            yield self.write(self.horiz_scale_write(scale))
        resp = yield self.query(self.horiz_scale_query(scale))
        returnValue(self.horiz_scale_parse(resp))

    @inlineCallbacks
    def horiz_position(self, position):
        """Get or set the horizontal position.

        Args:
            position: The position in XXX units.

        Returns:
            The resulting position.
        """
        if position is not None:
            yield self.write(self.horiz_position_write())
        resp = yield self.query(self.horiz_position_query())
        returnValue(self.horiz_position_parse(resp))

    # TRIGGER

    @inlineCallbacks
    def trigger_source(self, source=None):
        """Get or set the trigger source.

        Args:
            source: The source for the trigger. If None (the default) then we
                just query the current trigger source.

        Returns:
            The trigger source.
        """
        if source is not None:
            require_is_in(source, self.TRIGGER_SOURCES)
            yield self.write(self.trigger_source_write(source))
        resp = yield self.query(self.trigger_source_query())
        returnValue(self.trigger_source_parse(resp))

    @inlineCallbacks
    def trigger_slope(self, slope=None):
        """Get or set the trigger slope.

        Args:
            slope (str): Which slope to use for trigger.

        Returns:
            (str): The trigger slope.
        """
        if slope is not None:
            require_is_in(slope, self.TRIGGER_SLOPES)
            yield self.write(self.trigger_slope_write(slope))
        q = self.trigger_slope_query()
        resp = yield self.query(q)
        returnValue(self.trigger_slope_parse(resp))

    @inlineCallbacks
    def trigger_level(self, level=None):
        """Get or set the trigger level.

        Args:
            level: The trigger level.

        Returns:
            (Value[V]): The trigger level.
        """
        if level is not None:
            yield self.write(self.trigger_level_write(level))
        resp = yield self.query(self.trigger_level_query())
        returnValue(self.trigger_level_parse(resp))

    # ACQUISITION

    def get_trace(self, channel):
        raise NotImplementedError

