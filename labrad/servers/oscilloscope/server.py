"""
### BEGIN NODE INFO
[info]
name = Oscilloscope Server
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
from labrad.servers.oscilloscope.agilent.DSOX4104A import DSOX4104AWrapper
from labrad.servers.oscilloscope.agilent.DSO91304A import DSO91304AWrapper


class OscilloscopeServer(GPIBManagedServer):
    """Manges communication with oscilloscopes. ALL the oscilloscopes."""

    name = 'Oscilloscope Server'

    deviceWrappers = {
            'AGILENT TECHNOLOGIES DSO-X 4104A': DSOX4104AWrapper,
            'KEYSIGHT TECHNOLOGIES DSO90804A': DSO91304AWrapper,
    }

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

    @setting(50, channel='i', state='b', returns='b')
    def channel_on(self, c, channel, state=None):
        """Set or query channel on/off state.

        Args:
            channel (int): Which channel.
            state (bool): True->On, False->Off. If None (default), then we
                only query the state without setting it.

        Returns:
            (bool): The channel state.
        """
        return self.selectedDevice(c).channel_on(channel, state)

    @setting(51, channel='i', coup='s', returns='s')
    def coupling(self, c, channel, coup=None):
        """Set or query channel coupling.

        Args:
            channel (int): Which channel to set coupling.
            coup (str): Coupling, 'AC' or 'DC'. If None (the default) just query
                the coupling without setting it.

        Returns:
            string indicating the channel's coupling.
        """
        return self.selectedDevice(c).coupling(channel, coup)

    @setting(52, channel='i', invert='b', returns='b')
    def invert(self, c, channel, invert=None):
        """Get or set channel inversion.

        Args:
            channel (int):
            invert (bool): True->invert channel, False->do not invert channel.
                If None (the default), then we only query the inversion.

        Returns:
            (int): 0: not inverted, 1: inverted.
        """
        return self.selectedDevice(c).invert(channel, invert)

    @setting(53, channel='i', term='i', returns='i')
    def termination(self, c, channel, term=None):
        """Set channel termination

        Args:
            channel (int): Which channel to set termination.
            term (int): Termination in Ohms. Either 50 or 1,000,000.
        """
        return self.selectedDevice(c).termination(channel, term)

    # VERTICAL

    @setting(20, channel='i', scale='v[V]', returns='v[V]')
    def scale(self, c, channel, scale=None):
        """Get or set the vertical scale.

        Args:
            channel (int): The channel to get or set.
            scale (Value[V]): The vertical scale, i.e. voltage per division. If
                None (the default), we just query.

        Returns:
            Value[V]: The vertical scale.
        """
        return self.selectDevice(c).vert_scale(channel, scale)

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
        return self.selectedDevice(c).vert_position(channel, position)

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
        return self.selectedDevice(c).horiz_scale(scale)

    @setting(31, position='v[]', returns='v[]')
    def horiz_position(self, c, position=None):
        """Set or query the horizontal position.

        Args:
            position (float): Horizontal position in units of division.

        Returns:
            (float): The horizontal position in units of divisions.
        """
        return self.selectedDevice(c).horiz_position(position)

    # TRIGGER

    @setting(71, source='s', returns='s')
    def trigger_source(self, c, source=None):
        """Set or query trigger source.

        Args:
            source (str): 'EXT', 'LINE', 'CHANX' where X is channel number. If
                None (the default) then we just query.

        Returns:
            (str): Trigger source.
        """
        return self.selectedDevice(c).trigger_source(source)

    @setting(72, slope='s', returns='s')
    def trigger_slope(self, c, slope=None):
        """Set or query trigger slope.

        Args:
            slope (str): Trigger slope. If None, the default, we just query.
                Allowed values are 'POS' and 'NEG'.

        Returns:
            (str): The trigger slope.
        """
        return self.selectDevice(c).trigger_slope(slope)

    @setting(73, level='v[V]', returns='v[V]')
    def trigger_level(self, c, level=None):
        """Set or query the trigger level.

        Args:
            level (Value[V]): Trigger level. If None (the default), we just
                query.

        Returns:
            (Value[V]): The trigger level.
        """
        return self.selectedDevice(c).trigger_level(level)

    @setting(74, mode='s', returns='s')
    def trigger_mode(self, c, mode=None):
        """Set or query the trigger mode.

        Args:
            mode (str): The trigger mode to set. If None, we just query.

        Returns (str): The trigger mode.
        """
        return self.selectedDevice(c).trigger_mode(mode)

    # ACQUISITION

    @setting(60, average_on='b', returns='b')
    def average_on_off(self, c, average_on=None):
        """Turn averaging on or off.

        Args:
            average_on (bool): If True, turn averaging on.

        Returns (bool): Whether averaging is one or off.
        """
        return self.selectedDevice(c).average_on_off(average_on)

    @setting(61, averages='i', returns='i')
    def average_number(self, c, averages=None):
        """Set number of averages.

        Args:
            averages (int): Number of averages.

        Returns (int): Number of averages.
        """
        return self.selectedDevice(c).average_number(averages)

    @setting(68, channel='i', returns='*v[s]*v[V]')
    def get_trace(self, c, channel):
        """Get a trace for a single channel.

        Args:
            channel: The channel for which we want to get the trace.

        Returns:
            (ValueArray[s]): Time axis.
            (ValueArray[V]): Voltages.
        """
        return self.selectedDevice(c).get_trace(channel)


if __name__ == '__main__':
    from labrad import util
    util.runServer(OscilloscopeServer())
