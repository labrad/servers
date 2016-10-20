from __future__ import absolute_import

import numpy
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T
from labrad.gpib import GPIBDeviceWrapper


def filter_function(*allowed):
    def func(x):
        if x not in allowed:
            raise ValueError("{} not allowed because not in {}".format(allowed))
        return x
    return func


def channel_method(input_parser, write, query, output_parser):
    @inlineCallbacks
    def func(self, channel, arg=None):
        if arg is not None:
            yield self.write(write(channel, input_parser(arg)))
        resp = yield self.query(query(channel))
        returnValue(output_parser(resp))
    return func


def global_method(input_parser, write, query, output_parser):
    @inlineCallbacks
    def func(self, arg=None):
        if arg is not None:
            yield self.write(write(input_parser(arg)))
        resp = yield self.query(query())
        returnValue(output_parser(resp))
    return func


class OscilloscopeWrapper(GPIBDeviceWrapper):
    """Base class for oscilloscope wrappers"""

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
    def channel_on(self, channel, state=None):
        """Get or set channel on/off.

        Args:
            channel (int): The channel to get or set.
            state (bool): True->On, False->Off.

        Returns:
            (bool): State of the channel.
        """
        raise NotImplementedError()

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
        raise NotImplementedError()

    @inlineCallbacks
    def invert(self, channel, invert):
        """Get or set channel inversion.

        Args:
            channel (int): Which channel to get or set.
            invert (bool): True->invert, False->no invert. If None (the
                default), then we just query.

        Returns:
            (bool): Whether or not the channel is iverted.
        """
        raise NotImplementedError()

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
        raise NotImplementedError()

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
        raise NotImplementedError()

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
        raise NotImplementedError()

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
        raise NotImplementedError()

    @inlineCallbacks
    def horiz_position(self, position):
        """Get or set the horizontal position.

        Args:
            position: The position in XXX units.

        Returns:
            The resulting position.
        """
        raise NotImplementedError()

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
        raise NotImplementedError()

    @inlineCallbacks
    def trigger_slope(self, slope=None):
        """Get or set the trigger slope.

        Args:
            slope (str): Which slope to use for trigger.

        Returns:
            (str): The trigger slope.
        """
        raise NotImplementedError()

    @inlineCallbacks
    def trigger_level(self, level=None):
        """Get or set the trigger level.

        Args:
            level (Value[V]): The trigger level.

        Returns:
            (Value[V]): The trigger level.
        """
        raise NotImplementedError()

    # ACQUISITION

    def get_trace(self, channel):
        raise NotImplementedError()

