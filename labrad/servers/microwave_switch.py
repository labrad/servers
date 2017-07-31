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

# Changelog
# 1.1 Initial release
# 1.2 Modify to support multiple switches

"""
### BEGIN NODE INFO
[info]
name = Microwave Switch
version = 1.2
description = Microwave switch connecting the GHz DACs to the spectrum analyzer

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, util
from labrad.errors import Error
from labrad.types import Value
from labrad.server import LabradServer, setting
import labrad.servers.ghzdac.keys as keys
from twisted.python import log
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue
from time import sleep
from ctypes import windll, create_string_buffer, c_byte
from types import ListType, IntType

class ChannelNotConfiguredError(Error):
    """No switch position has been configured for this board.
    Use GHz_DAC_calibrate to configure it."""
    code = 1
class NoSuchChannelError(Error):
    """This switch position does not exist"""
    code = 2
class NoDeviceSelectedError(Error):
    """No Darlington board device has been selected in this context."""
    code = 3
    
class MicrowaveSwitch(LabradServer):

    name = 'Microwave Switch'

    # TODO: move to registry
    deviceslist = [
        {
            'name': 'Vince GHzDAC IQ cal',
            'server': 'Vince Darlington Board',
            'boardname': '14A8411',
            'bits': [[36,37,38,39,40,41,42],48,47,46,45,44,43],
            # whether the switch resets automatically when changing to another setting
            'autoreset': False,
            # on-off delay
            'delay': 0.10
        }
        ,{
            'name': 'Jules GHzDAC IQ cal',
            'server': 'DR Darlington Board',
            'boardname': '14A123362',
            'bits': [7,1,2,3,4,5,6],
            'autoreset': True,
            'delay': 0.05
        }
    ]

    devices = []
    
    @inlineCallbacks
    def initServer(self):
        cxn = self.client
        devices = []
        for dev in self.deviceslist:
            for n, s in cxn.servers.items():
                if n == dev['server']:
                    print "found server"
                    listdevs = yield cxn[dev['server']].list_devices()
                    for number, name in listdevs:
                        print "devname:", name
                        if name == dev['boardname']:
                            print "found device"
                            self.devices.append(dev)
                            yield cxn[dev['server']].select_device(dev['boardname'])
                            for i in dev['bits']:
                                if type(i)==IntType:
                                    yield cxn[dev['server']].set_bit(i,False)
                                elif type(i)==ListType:
                                    for j in i:
                                        yield cxn[dev['server']].set_bit(j,False)

        
    @setting(0, 'List Devices', returns=['*(ws): List of uWave switches'])
    def list_devices(self, c):
        return([(i,n['name']) for i,n in enumerate(self.devices)])
        
    @setting(10, 'Select Device',
                 dev=[': connect to first available switch',
                        'w: connect to nth available switch',
                       's: connect to switch with name'],
                 returns=['s: selected switch'])
    def select_device(self, c, dev):
        print 'Selecting switch: ', dev
        if dev is None:
            c['device'] = self.devices[0]
        elif isinstance(dev, (int,long)):
            if dev >= len(self.devices):
                raise NoSuchDeviceError()
            c['device'] = self.devices[dev]
        elif isinstance(dev, str):
            match = False
            for i in self.devices:
                if i['name'] == dev:
                    c['device'] = i
                    match = True
            if not match:
                raise NoSuchDeviceError()
        else:
            raise NoSuchDeviceError()
        return c['device']['name']
            
        
    # labrad wrapper for performing the switching
    @inlineCallbacks
    @setting(20, 'Switch', channel=['w: switch position (0 for all open)',
                                    's: connect to FPGA board (empty for all open)'],
            returns=['w: switch position'])
    def switch(self, c, channel):
        cxn = self.client
        
        if isinstance(channel, str):
            if channel == '':
                channel = 0
            else:
                try:
                    # Get the switch that's connected to the DAC from the registry
                    dev = cxn.registry.packet().\
                    cd(['',keys.SESSIONNAME,channel]).\
                    get(keys.SWITCHNAME)
                    print dev
                    dev = yield dev.send()
                    dev = dev.get
                    yield self.select_device(c, dev)

                    # Get the channel number corresponding to the DAC from the registry
                    channel = cxn.registry.packet().\
                    cd(['',keys.SESSIONNAME,channel]).\
                    get(keys.SWITCHPOSITION)
                    channel = yield channel.send()
                    channel = channel.get
                
                except:
                    raise ChannelNotConfiguredError()

        if 'device' not in c:
            raise NoDeviceSelectedError()
        
        if channel < 0 or channel > len(c['device']['bits']):
            raise NoSuchChannelError()

        # Reset the switch first if it doesn't auto-reset, otherwise the behavior is undefined
        if(channel != 0 and c['device']['autoreset']==False):
            yield self.doSwitch(c, 0)

        yield self.doSwitch(c, channel)

        returnValue(channel)

    # Actually perform the switch change
    @inlineCallbacks
    def doSwitch(self, c, channel):
        cxn = self.client
        if type(c['device']['bits'][channel])==IntType:
            yield cxn[c['device']['server']].sequence([\
                (c['device']['bits'][channel], True, Value(c['device']['delay'],'s')),
                (c['device']['bits'][channel], False, Value(c['device']['delay'],'s'))])
        elif type(c['device']['bits'][channel])==ListType:
            # start assembling the multi-switch sequence
            seq = []
            # open all darlington switches but the last one without any delays
            for i in range(len(c['device']['bits'][channel])-1):
                seq.append((c['device']['bits'][channel][i], True, Value(0,'s')))
            # add a delay to the last one so that the mechanical switch can actuate once it has sufficient current
            seq.append((c['device']['bits'][channel][len(c['device']['bits'][channel])-1], True, Value(c['device']['delay'],'s')))
            # close all the darlington switches afterwards
            for i in range(len(c['device']['bits'][channel])-1):
                seq.append((c['device']['bits'][channel][i], False, Value(0,'s')))
            seq.append((c['device']['bits'][channel][len(c['device']['bits'][channel])-1], False, Value(c['device']['delay'],'s')))
            yield cxn[c['device']['server']].sequence(seq)
                
__server__ = MicrowaveSwitch()
            
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)         
                 
             
