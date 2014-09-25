# Copyright (C) 2014  Peter O'Malley
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
name = DAC Emulator
version = 1.0
description = A DAC emulator.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

'''
How to define DACs to be emulated:
-- In the registry, under >> Servers >> DAC Emulator
-- One folder for each DAC, with the DAC's name as folder name
-- Recognized keys (* = can be changed with server function)
    address         *(MAC address)
    device          (what ethernet device (NIC) number to emulate on)
    build           (DAC build number)
    SRAM Length     *(in bytes)
    plotting        *(boolean--whether to plot SRAM on run.)
'''

# doo dee doop, just a dac emulator

import time
import sys
import string

import numpy as np
import matplotlib.pyplot as plt

from twisted.internet import defer, reactor, task
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.server import LabradServer, setting
from labrad.devices import DeviceServer, DeviceWrapper

import ethernet_spoofer as es

REGISTRY_PATH = ['', 'Servers', 'DAC Emulator']

DEFAULT_DEVICE = 0
DEFAULT_MAC = '11:22:33:44:55:66'
DEFAULT_BUILD = 0
DEFAULT_SRAM_LENGTH = 10240

def _convertTwosComplement(data):
    ''' convert from 14-bits-in-32-bit-unsigned
    to 14-bits-2s-complement-in-32-bit-unsigned. '''
    d = data.astype(np.int32)
    d[d > 2**13 - 1] = d[d > 2**13 - 1] - 2**14
    return d

class DacEmulator (DeviceWrapper):
    
    def connect(self, *args, **kwargs):
        print "Creating emulator with %s" % str(kwargs)
        # set up spoofer
        address = kwargs.get("address", DEFAULT_MAC)
        device = kwargs.get("device", DEFAULT_DEVICE)
        self.spoof = es.EthernetSpoofer(address, device)
        # set up DAC
        self.build = kwargs.get("build", DEFAULT_BUILD)
        self.sram_length = kwargs.get("SRAM Length", DEFAULT_SRAM_LENGTH)
        self.initRegister()
        self.initSRAM()
        
        # other options
        self.plotting = kwargs.get("plotting", False)
        
        # run the loop
        self.loop = task.LoopingCall(self.next_packet)
        self.loopDone = self.loop.start(0.1)
        
    def shutdown(self):
        self.loop.stop()
        yield self.loopDone
        del self.loop
        
    def next_packet(self):
        ''' handle next packet '''
        packet = self.spoof.getPacket()
        if not packet:
            return
        if packet['length'] == 1026:
            # we have an SRAM write packet
            adrstart = 256*ord(packet['data'][0]) + \
                           256*256*ord(packet['data'][1])
            if adrstart > self.sram_length - 256:
                print "Bad SRAM packet: adrstart too big: %s" % adrstart
                return
            print "Writing SRAM at derp %s" % (adrstart / 256)
            self.sram[adrstart:adrstart+256] = \
                np.fromstring(packet['data'][2:], '<u4')
        elif packet['length'] == 56:
            # register packet
            self.register = np.fromstring(packet['data'], '<u1')
            if packet['data'][1] == '\x01':
                self.registerReadback(packet['src'])
        else:
            print "From %s : %s" % (packet['src'], packet['data'])
                
    def registerReadback(self, dest):
        packet = np.zeros(70, '<u1')
        packet[0:51] = self.register[0:51]
        packet[51] = self.build
        
        print "Register readback send: %s" \
            % str(self.send(dest, packet.tostring()))

    def initRegister(self):
        self.register = np.zeros(56, '<u1')
        
    def initSRAM(self):
        self.sram = np.zeros(self.sram_length, '<u4')
        
    def plotSRAM(self):
        dacA = self.sram & 0x3FFF # first 14 bits
        dacB = self.sram >> 14 & 0x3FFF # second 14 bits
        dacA, dacB = _convertTwosComplement(dacA), _convertTwosComplement(dacB)
        ax = plt.figure().add_subplot(111)
        ax.plot(dacA, 'b.')
        ax.plot(dacB, 'r.')
        ax.set_xlim(0, 10240)
        ax.set_ylim(-2**13 -1, 2**13-1)
        plt.show()
        
    def send(self, dest, data):
        return self.spoof.sendPacket(dest, data)

class DacEmulatorServer(DeviceServer):
    name = "DAC Emulator"
    deviceName = "DAC Emulator"
    deviceWrapper = DacEmulator
        
    @inlineCallbacks
    def findDevices(self):
        '''Create DAC emulators.'''
        reg = self.client.registry
        yield reg.cd(REGISTRY_PATH)
        resp = yield reg.dir()
        names = resp[0].aslist
        devs = []
        for n in names:
            yield reg.cd(n)
            keys = yield reg.dir()
            keys = keys[1].aslist
            p = reg.packet()
            for k in keys:
                p.get(k, key=k)
            a = yield p.send()
            devs.append((n, [], dict([(k, a[k]) for k in keys])))
            reg.cd(1)
        returnValue(devs)
        
    @setting(10, 'Address', mac='s', returns='s')
    def address(self, c, mac=''):
        '''get/set the MAC address'''
        dev = self.selectedDevice(c)
        if mac:
            dev.spoof.setAddress(mac)
        return dev.spoof.mac
        
    @setting(11, 'Send', dest='s', data='s', returns='?')
    def send(self, c, dest, data):
        '''
        Send a packet, to destination mac "dest", with data "data". returns 0
        for success, error message otherwise
        '''
        return self.selectedDevice(c).send(dest, data)
        
    @setting(20, 'Plotting', on='b', returns='b')
    def plotting(self, c, on=None):
        ''' get / set plotting mode '''
        dev = self.selectedDevice(c)
        if on is not None:
            dev.plotting = on
        return dev.plotting
        
    @setting(21, "SRAM Length", len='w', returns='w')
    def sram_length(self, c, len=None):
        '''Get or set(!) the SRAM length. Note that this clears the SRAM.'''
        dev = self.selectedDevice(c)
        if len:
            dev.sram_length = len
            dev.initSRAM()
        return dev.sram_length
        
    @setting(22, "Plot SRAM")
    def plot_sram(self, c):
        '''Plots the SRAM.'''
        self.selectedDevice(c).plotSRAM()

__server__ = DacEmulatorServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
