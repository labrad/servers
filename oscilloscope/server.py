"""
### BEGIN NODE INFO
[info]
name = Oscilloscope
version = 0.1
description = Talks to oscilloscopes

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""


from __future__ import absolute_import

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.gpib import GPIBManagedServer
from labrad.server import setting
import oscilloscope.agilent as agilent


class OscilloscopeServer(GPIBManagedServer):
    """Manges communication with oscilloscopes. ALL the oscilloscopes."""

    name = 'Oscilloscope Server'

    deviceWrappers = {
            'AGILENT TECHNOLOGIES DSO-X 4104A': agilent.AgilentDSOX4104AWrapper}

    # SYSTEM

    @setting(11, returns='')
    def reset(self, c):
        """Reset the oscilloscope to factory settings."""
        dev = self.selectedDevice(c)
        yield dev.reset()

    @setting(12, returns='')
    def clear_buffers(self, c):
        """Clear device status buffers."""
        dev = self.selectedDevice(c)
        yield dev.clear_buffers()

    # CHANNEL

    @setting(50, channel='i', state='s', returns='s')
    def channel_on_off(self, c, channel, state=None):
        dev = self.selectedDevice(c)
        result = yield dev.channel_on_off(channel, state)
        returnValue(result)

    @setting(51, channel='i', coup='s', returns='s')
    def coupling(self, c, channel, coup=None):
        """Set or query channel coupling.

        Args:
            channel (int): Which channel to set coupling.
            coup (str): Coupling (usually 'AC' or 'DC'). If None (the default)
                just query the coupling without setting it.

        Returns:
            string indicating the channel's coupling.
        """
        dev = self.selectedDevice(c)
        result = yield dev.coupling(channel, coup)
        returnValue(result)

    @setting(52, channel='i', invert='i', returns='i')
    def invert(self, c, channel, invert=None):
        """Get or set channel inversion.

        Args:
            channel (int):
            invert (int): 1 -> invert channel, 0 -> do not invert channel. If
                None (the default), then we only query the inversion.

        Returns:
            (int): 0: not inverted, 1: inverted.
        """
        dev = self.selectedDevice(c)
        result = yield dev.invert(channel, invert)
        returnValue(result)

    @setting(53, channel='i', term='i', returns='i')
    def termination(self, c, channel, term=None):
        """Set channel termination

        Args:
            channel (int): Which channel to set termination.
            term (int): Termination in Ohms. Either 50 or 1,000,000 on every
                scope known to mankind.
        """
        dev = self.selectedDevice(c)
        result = yield dev.termination(channel, term)
        returnValue(result)

    # VERTICAL

    @setting(20, channel='i', scale='v[V]', returns='v[V]')
    def scale(self, c, channel, scale=None):
        dev = self.selectedDevice(c)
        result = yield dev.vert_scale(channel, scale)
        returnValue(result)

    @setting(21, channel='i', position='v[]', returns='v[]')
    def position(self, c, channel, position=None):
        """Get or set the vertical position.

        Args:
            channel (int): Which channel to get/set.
            position (float): Vertical position in units of divisions. If None,
                (the default), then we only query.

        Returns:
            (float): Vertical position in units of divisions.
        """
        dev = self.selectedDevice(c)
        result = yield dev.vert_position(channel, position)
        returnValue(result)

    # HORIZONTAL

    @setting(30, scale='v[s]', returns='v[s]')
    def horiz_scale(self, c, scale=None):
        """Set or query the horizontal scale.

        Args:
            scale (Value[s]): Horizontal scale, i.e. time per division. If None,
                (the default), then we just query.

        Returns:
            (Value[s]): The horizontal scale.
        """
        dev = self.selectedDevice(c)
        result = yield dev.horiz_scale(scale)
        returnValue(result)

    @setting(31, position='v[]', returns='v[]')
    def horiz_position(self, c, position=None):
        """Set or query the horizontal position.

        Args:
            position (float): Horizontal position in units of division.

        Returns:
            (float): The horizontal position in units of divisions.
        """
        dev = self.selectedDevice(c)
        result = yield dev.horiz_position(position)
        returnValue(result)

    # TRIGGER

    @setting(71, source=['s'], returns='s')
    def trigger_source(self, c, source=None):
        """Set or query trigger source.

        Args:
            source (str): 'EXT', 'LINE', 'CHANX' where X is channel number. If
                None (the default) then we just query.

        Returns:
            (str): Trigger source.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.trigger_source(source)
        returnValue(resp)

    @setting(72, slope='s', returns='s')
    def trigger_slope(self, c, slope=None):
        """Set or query trigger slope.

        Args:
            slope (str): Trigger slope. If None, the default, we just query.
                Allowed values are 'POS' and 'NEG'.

        Returns:
            (str): The trigger slope.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.trigger_slope(slope)
        returnValue(resp)

    @setting(73, level='v[V]', returns='v[V]')
    def trigger_level(self, c, level=None):
        """Set or query the trigger level.

        Args:
            level (Value[V]): Trigger level. If None (the default), we just
                query.

        Returns:
            (Value[V]): The trigger level.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.trigger_level(level)
        returnValue(resp)

    # ACQUISITION

    @setting(60, channel='i', returns='*v[s]*v[V]')
    def get_trace(self, c, channel):
        """Get a trace for a single channel.

        Args:
            channel: The channel for which we want to get the trace.

        Returns:
            (ValueArray[s]): Time axis.
            (ValueArray[V]): Voltages.
        """
        dev = self.selectedDevice(c)
        result = yield dev.get_trace(channel)
        returnValue(result)


__server__ = OscilloscopeServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
