#!c:\python25\python.exe

# Copyright (C) 2008  Max Hofheinz
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

from labrad import types as T, util
from labrad.errors import Error
from labrad.types import Value
from labrad.server import LabradServer, setting
import ghzdac.keys as keys
from twisted.python import log
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue
from time import sleep
from ctypes import windll, create_string_buffer, c_byte

class ChannelNotConfiguredError(Error):
    """No switch position has been configured for this board.
    Use GHz_DAC_calibrate to configure it."""
    code = 1
class NoSuchChannelError(Error):
    """This switch position does not exist"""
    code = 2
    

    
class MicrowaveSwitch(LabradServer):

    name = 'Microwave Switch'

    driverboard = {
        'server': 'T1000 Darlington Board',
        'boardname': '14A123362',
        'bits': [7,1,2,3,4,5,6]
    }
    
    @inlineCallbacks
    def initServer(self):
        cxn = self.client
        yield cxn[self.driverboard['server']].\
              list_devices()
        yield cxn[self.driverboard['server']].\
              select_device(self.driverboard['boardname'])
        for i in self.driverboard['bits']:
            yield cxn[self.driverboard['server']].set_bit(i,False)
    
        
    @setting(10, 'Switch', channel=['w: switch position (0 for all open)',
                                    's: connect to FPGA board (empty for all open)'],
            returns=['w: switch position'])
    def switch(self, c, channel):
        cxn = self.client
        if isinstance(channel, str):
            if channel == '':
                channel = 0
            else:
                try:
                    channel = cxn.registry.packet().\
                    cd(['',keys.SESSIONNAME,channel]).\
                    get(keys.SWITCHPOSITION)
                    channel = yield channel.send()
                    channel = channel.get
                except:
                    raise ChannelNotConfiguredError()
        if channel < 0 or channel > len(self.driverboard['bits']):
            raise NoSuchChannelError()
        yield cxn[self.driverboard['server']].sequence([\
            (self.driverboard['bits'][channel], True, Value(0.05,'s')),
            (self.driverboard['bits'][channel], False, Value(0,'s'))])
        returnValue(channel)
        
__server__ = MicrowaveSwitch()
            
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)         
                 
             
