# Copyright (C) 2012 Peter O'Malley
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
name = Agilent Switch
version = 0.2
description = Agilent 34980A Matrix Switch

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

# notes
# the 34932A matrix module can switch up to 100 times a second.
# we have two cards. logical rows 1-4 correspond to rows 1-4 on card 1, and 5-8 with rows 1-4 on card two.
# the rows are shorted across the two matrices on each card
# logical columns 1-16 correspond to columns 1-16 on matrix 1 (cards 1 and 2)
# 17-32 with cols 1-16 on matrix 2. the cols are shorted across the two cards.
# therefore, "connect row 7 and col 17" means to close row 3 and col 1 on card 2, matrix 2
# while "connect row 2 and col 2" means to close row 2 and col 2 on card 1, matrix 1
# finally, note that if you're on matrix 2, then the rows are numbered 5-8
# so actually, "connect row 7 and col 17" means close row 7 and col 1 on card 2, (using matrix 2)
# while "connect row 7 and col 16" means close row 3 and col 16 on card 2 (using matrix 1)

from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
import numpy as np
from twisted.internet.defer import inlineCallbacks, returnValue

def convertPoint(row, col, config='4x64'):
    ''' go from logical row/col to physical card/row/col.

    This function takes a high level matrix address and determines
    the correct row and column on the physical card.

    Args:
        config (str):  This specifies the physical connections of
            the matrix switch or switches.  Default is 8 by 32,
            but 4 by 64 is also supported.
    '''
    if config == '4x64':
        if row < 1 or row > 4 or col < 1 or col > 64:
            raise ValueError("Row must be 1-4, col must be 1-64.")
        # which card are we on?
        card = 1
        if col > 32:
            card = 2
            col -= 32
        if col > 16:
            row += 4
            col -= 16
    else:
        if row < 1 or row > 8 or col < 1 or col > 32:
            raise ValueError("Row must be 1-8, col must be 1-32.")
        # which card are we on?
        if row > 4:
            card = 2
            row -= 4
        if col > 16:
            row += 4
            col -= 16
    return "%i%i%02i" % (card, row, col)


class AgilentSwitchWrapper(GPIBDeviceWrapper):
    #@inlineCallbacks
    def initialize(self):
        self.states = {}

        
class AgilentSwitchServer(GPIBManagedServer):
    name = 'Agilent Switch'
    deviceName = 'Agilent Technologies 34980A'
    deviceWrapper = AgilentSwitchWrapper
    
    @setting(10, 'Connect', row='i', col='i', close='b', config='s')
    def connect(self, c, row, col, close=True, config='4x64'):
        ''' Connect a given row to column. Disconnect if close=False.

        Connect or disconnect a connection point specified by row and
        column.
        Args:
            row (int): Row specifying the desired connection point.
            col (int): Column specifying the desired connection point.
            close (bool):  True: close connection point
                           False:  open connection points
            config (str):  Matrix switch configuration: '4x64' supported
                and '8x32' is the default.
        '''
        dev = self.selectedDevice(c)
        count = 0
        success = False
        while not success and count < 10:
            if close:
                dev.write("ROUT:CLOS (@%s)" % convertPoint(row, col, config))
                resp = yield dev.query("ROUT:CLOS? (@{})".format(convertPoint(row, col,
                                                                              config)))
            else:
                dev.write("ROUT:OPEN (@%s)" % convertPoint(row, col, config))
                resp = yield dev.query("ROUT:OPEN? (@{})".format(convertPoint(row, col,
                                                                              config)))
            # print resp, bool(int(resp))
            resp = bool(int(resp))

            success = resp
            if not resp:
                print 'ERROR! Attempt {}: Route not connected/open as ' \
                      'requested! row: {}; col{}; close: {}, ' \
                      'config: {}'.format(count, row, col, close, config)
            count += 1

        if count > 10:
            raise Exception('ERROR!  10 failed attempts to close({}) row ({}) '
                            'and col ({})'.format(close, row, col))


    @setting(11, 'Open All')
    def open_all(self, c):
        ''' Open all channels. '''
        self.selectedDevice(c).write("ROUT:OPEN:ALL ALL")

    @setting(12, 'Close Analog Bus', close='b')
    def close_analog_bus(self, c, close=True):
        """This function closes the analog bus to connect rows between slots 1&2

        This allows for two 34932A modules to operate in a 4x64 mode.  The
        analog bus connects the rows between modules.  In this case it is
        coded to connect or disconnect the four rows in both module
        1 and 2 to the analog bus.
        Args:
            close (bool):  True: connect; False: disconnect
        """
        dev = self.selectedDevice(c)
        if close:
            dev.write("ROUT:CLOS (@1921, 1922, 1923, 1924)")
            dev.write("ROUT:CLOS (@2921, 2922, 2923, 2924)")
        else:
            dev.write("ROUT:OPEN (@1921, 1922, 1923, 1924)")
            dev.write("ROUT:OPEN (@2921, 2922, 2923, 2924)")

    @setting(20, 'Define State', id='i', connections='*(ii)')
    def define_state(self, c, id, connections):
        ''' Define a state. id is the index of the state.
        connections is a list of row, col pairs.
        This state can then be recalled with set_state, read with get_state, and removed with delete_state.'''
        self.selectedDevice(c).states[id] = connections
    
    @setting(21, 'Delete State', id='i', returns='*(ii)')
    def delete_state(self, c, id):
        ''' Remove/undefine a state. '''
        return self.selectedDevice(c).states.pop(id)
        
    @setting(22, 'Get State', id='i', returns='*(ii)')
    def get_state(self, c, id):
        ''' Returns the connections that define this state. '''
        return self.selectedDevice(c).states[id]
        
    @setting(23, 'Set State', id='i', returns='*(ii)')
    def set_state(self, c, id):
        ''' Activates this state. '''
        dev = self.selectedDevice(c)
        state = dev.states[id]
        dev.write("ROUT:CLOS:EXCL (@%s)" % ','.join([convertPoint(r, c) for r, c in state]))
        return state

    @setting(24, 'Check Relay Count', returns='**i')
    def check_relay_count(self, c, config='4x64'):
        '''Check the relay count for all connection points.

        Returns a 2D array of integers, rows and columns correspond to index 1
        and 2 respectively in the matrix.  This shows the relay connection count
        for each connection point.  For this module under a 10V load, it expects
        at least 1M cycles, but if a faulty relay is suspected, high relay counts
        are suspect.
        Args:
            config (str):  config (str):  Matrix switch configuration: '4x64' supported
                and '8x32' is the default.
        '''
        dev = self.selectedDevice(c)
        if config == '4x64':
            rows = [1, 2, 3, 4]
            cols = np.linspace(1, 64, 64)
        else:
            raise Exception('Error!  This function only implemented for 4x64 '
                            'matrix configuration. Requested {}'.format(config))
        counts = []
        for row in rows:
            column_counts = []
            for col in cols:
                resp = yield dev.query(':DIAG:REL:CYCL? (@%s)' % convertPoint(row, col, config))
                column_counts.append(int(resp))
            counts.append(column_counts)
        yield counts
        returnValue(counts)

    @setting(25, 'Find Closed Relays', returns='**i')
    def find_closed_relays(self, c, config='4x64'):
        """This function returns a list of currently close connection points.

        Just a useful debugging tool.  Note: this only queries the software
        state of the relays i.e. it would not 'catch' a bad or sticky relay
        that was failing to actuate.
        Args:
            config (str): config (str):  Matrix switch configuration, only
                '4x64' is supported as-is, others can be implemeted.
        """
        dev = self.selectedDevice(c)
        if config == '4x64':
            rows = [1, 2, 3, 4]
            cols = np.linspace(1, 64, 64)
        else:
            raise Exception('Error!  This function only implemented for 4x64 '
                            'matrix configuration. Requested {}'.format(config))
        closed = []
        for row in rows:
            for col in cols:
                col = int(col)
                resp = yield dev.query(':ROUT:CLOS? (@{})'
                                       ''.format(convertPoint(row, col, config)))
                if bool(int(resp)):
                    closed.append([row, col])
        yield closed
        returnValue(closed)

__server__ = AgilentSwitchServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
