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
version = 0.1
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
from twisted.internet.defer import inlineCallbacks, returnValue

def convertPoint(row, col):
    ''' go from logical row/col to physical card/row/col. '''
    if row < 1 or row > 8 or col < 1 or col > 32:
        raise ValueError("Row must be 1-8, col must be 1-32.")
    # which card are we on?
    card = 1
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
    
    @setting(10, 'Connect', row='i', col='i', close='b')
    def connect(self, c, row, col, close=True):
        ''' Connect a given row to column. Disconnect if close=False. '''
        dev = self.selectedDevice(c)
        if close:
            dev.write("ROUT:CLOS (@%s)" % convertPoint(row, col))
        else:
            dev.write("ROUT:OPEN (@%s)" % convertPoint(row, col))
            
    @setting(11, 'Open All')
    def open_all(self, c):
        ''' Open all channels. '''
        self.selectedDevice(c).write("ROUT:OPEN:ALL ALL")
        
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

__server__ = AgilentSwitchServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
