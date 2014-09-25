# Copyright (C) 2007  Matthew Neeley
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
name = Sequencer
version = 1.0
description = Talks to old DAC sequencer board

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, util
from labrad.devices import DeviceWrapper, DeviceServer
from labrad.server import setting
from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from array import array
from datetime import datetime, timedelta
from math import sin, cos

#NUMRETRIES = 1
SRAM_LEN = 7936
MEM_LEN = 256
BUILD = 1

class FPGADevice(DeviceWrapper):
    @inlineCallbacks
    def connect(self, de, port, board, build):
        print 'connecting to: %s (build #%d)' % (boardMAC(board), build)

        self.server = de
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = boardMAC(board)
        self.serverName = de.name

        self.sram = [0L] * SRAM_LEN
        self.sramAddress = 0
        self.mem = [0L] * MEM_LEN
        self.seqTime = 0 # estimated sequence runtime in seconds
        self.DACclocks = 0
        self.timeout = T.Value(1000, 'ms')

        # set up the direct ethernet server for this board
        # in our own context
        p = de.packet()
        p.connect(port)
        p.require_length(70)
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        p.timeout(self.timeout)
        p.listen()
        yield p.send(context=self.ctx)

    @inlineCallbacks
    def sendRegisters(self, packet, asWords=True):
        """Send a register packet and readback answer."""
        # do we need to clear waiting packets first?
        p = self.server.packet()
        p.write(words2str(packet))
        p.read()
        ans = yield p.send(context=self.ctx)
        src, dst, eth, data = ans.read
        if asWords:
            data = [ord(c) for c in data]
        returnValue(data)

    def sendRegistersNoReadback(self, packet):
        """Send a register packet but don't readback anything."""
        d = self.server.write(words2str(packet), context=self.ctx)
        return d.addCallback(lambda r: True)

    @inlineCallbacks
    def runSequence(self, slave, delay, reps, getTimingData=True):
        server, ctx = self.server, self.ctx

        pkt = [1, 3] + [0]*54
        #pkt[13:15] = reps & 0xFF, (reps >> 8) & 0xFF
        #pkt[43:45] = int(slave), int(delay)
        r = yield self.sendRegistersNoReadback(pkt)

        if not getTimingData:
            returnValue(r)

        # TODO: handle multiple timers per cycle
        npackets = reps/30
        totalTime = 2 * (self.seqTime * reps + 1)
        p = server.packet()
        p.timeout(T.Value(totalTime * 1000, 'ms'))
        p.read(npackets)
        ans = yield p.send(context=ctx)
        sdata = [ord(data[j*2+3]) + (ord(data[j*2+4]) << 8)
                 for j in range(30)
                 for src, dst, eth, data in ans.read]
        returnValue(sdata)

    @inlineCallbacks
    def sendSRAM(self, data):
        """Write SRAM data to the FPGA.

        The data is written at the position specified by self.sramAddress.
        Data is only written if it needs to be changed.
        """
        totallen = len(data)
        adr = startadr = (self.sramAddress + 255) & SRAM_LEN
        endadr = startadr + totallen
        current = self.sram[startadr:endadr]
        if data != current: # only send if the SRAM is new
            p = self.server.packet()
            while len(data) > 0:
                page, data = data[:256], data[256:]
                if len(page) < 256:
                    page += [0]*(256-len(page))
                pkt = [(adr >> 8) & 31, 0] + \
                      [(n >> j) & 255 for n in page for j in [0, 8, 16, 24]]
                p.write(words2str(pkt))
                adr += 256
            start = datetime.now()
            yield p.send(context=self.ctx)
            #print 'update time:', datetime.now() - start
            self.sram[startadr:endadr] = data
        self.sramAddress = endadr
        returnValue((startadr, endadr))

    @inlineCallbacks
    def sendMemory(self, data, cycles):
        """Write Memory data to the FPGA.

        At most one page of memory is written at address 0.
        Data is only written if it needs to be changed.
        """
        # try to estimate the time in seconds
        # to execute this memory sequence
        self.seqTime = sequenceTime(data)
        
        data = data[0:256] # only one page supported
        totallen = len(data)
        adr = startadr = 0
        endadr = startadr + totallen
        current = self.mem[startadr:endadr]
        if data != current: # only send if the MEM is new
            p = self.server.packet()
            while len(data) > 0:
                page, data = data[:256], data[256:]
                if len(page) < 256:
                    page += [0]*(256-len(page))
                pkt = [cycles & 0xFF, (cycles >> 8) & 0xFF, (adr >> 8)] + \
                      [(n >> j) & 0xFF for n in page for j in (0, 8, 16)]
                p.write(words2str(pkt))
                adr += 256
            yield p.send(context=self.ctx)
            self.mem[startadr:endadr] = data
        returnValue((startadr, endadr))

    @inlineCallbacks
    def runI2C(self, data):
        pkt = [0, 2] + [0]*54
        answer = []
        while data[:1] == [258]:
            data = data[1:]

        while len(data):
            cnt = min(8, len(data))
            i = 0
            while i < cnt:
                if data[i] == 258:
                    cnt = i
                i += 1

            stopI2C, readwriteI2C, ackI2C = (256 >> cnt) & 255, 0, 0
            cur = 128
            for i in range(cnt):
                if data[i] in [256, 257]:
                    readwriteI2C |= cur
                elif data[i] == 256:
                    ackI2C |= cur
                elif data[i] < 256:
                    pkt[12-i] = data[i]
                else:
                    pkt[12-i] = 0
                cur >>= 1

            pkt[2:5] = stopI2C, readwriteI2C, ackI2C

            r = yield self.sendRegisters(pkt)

            for i in range(cnt):
                if data[i] in [256, 257]:
                    answer += [r[61+cnt-i]]

            data = data[cnt:]
            while data[:1] == [258]:
                data = data[1:]

        returnValue(answer)


class FPGAServer(DeviceServer):
    name = 'Sequencer'
    deviceWrapper = FPGADevice
    possibleLinks = []

    #retryStats = [0] * NUMRETRIES
    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        yield self.loadConfigInfo()
        print 'done.'
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.client.registry
        p = reg.packet()
        p.cd(['', 'Servers', 'GHz DACs'], True)
        p.get('sequencer', key='links')
        ans = yield p.send()
        self.possibleLinks = ans['links'] #[(<name>, <EthernetServerName>, port),...]


    def initContext(self, c):
        c.update(daisy_chain=[], start_delay=[])

    @inlineCallbacks
    def findDevices(self):
        cxn = self.client
        found = []
        print self.possibleLinks
        for name, server, port in self.possibleLinks:
            if server not in cxn.servers:
                continue

            print 'Checking %s...' % name
            de = cxn.servers[server]
            ctx = cxn.context()
            adapters = yield de.adapters(context=ctx)
            if len(adapters):
                ports, names = zip(*adapters)
            else:
                ports, names = [], []
            if port not in ports:
                continue
            #MAC = names[list(ports).index(port)][-17:]
            
            # make a list of the boards currently known
            skips = {}
            for dname in self.devices:
                dev = self.devices[dname]
                if dev.serverName == de.name and dev.port == port:
                    skips[dev.board] = dev
            print 'skipping:', skips.keys()

            p = de.packet()
            p.connect(port)
            p.require_length(70)
            p.listen()

            # ping all boards
            for i in xrange(256):
                if i in skips:
                    found.append(skips[i].name)
                else:
                    p.destination_mac(boardMAC(i))
                    p.write(words2str([0, 1] + [0] * 54))
            yield p.send(context=ctx)

            # get ID packets from all boards
            for i in xrange(256):
                try:
                    ans = yield de.read(context=ctx)
                    src, dst, eth, data = ans
                    board, build = int(src[-2:], 16), ord(data[51])
                    if build != BUILD:
                        continue
                    devName = '%s FPGA %d' % (name, board)
                    args = de, port, board, build
                    found.append((devName, args))
                except T.Error:
                    #print 'timeout', i
                    pass # probably a timeout error

            # expire this context to stop listening
            yield cxn.manager.expire_context(de.ID, context=ctx)
        returnValue(found)


    @setting(20, 'SRAM Address', addr=['w'], returns=['w'])
    def sram_address(self, c, addr=None):
        """Sets the next SRAM address to be written to by SRAM."""
        dev = self.selectedDevice(c)
        if addr is None:
            addr = dev.sramAddress
        else:
            dev.sramAddress = addr
        return long(addr)


    @setting(21, 'SRAM', data=['*w: SRAM Words to be written'],
                         returns=['(ww): Start address, Length'])
    def sram(self, c, data):
        """Writes data to the SRAM at the current starting address."""
        dev = self.selectedDevice(c)
        return dev.sendSRAM(data)


    @setting(31, 'Memory', data=['*w: Memory Words to be written'],
                           returns=[''])
    def memory(self, c, data):
        """Writes data to the Memory at the current starting address."""
        dev = self.selectedDevice(c)
        c['mem'] = data
        #return dev.sendMemory(data)


    @setting(40, 'Run Sequence', reps=['w'], getTimingData=['b'],
                                 returns=['*2w', ''])
    def run_sequence(self, c, reps=30, getTimingData=True):
        """Executes a sequence on one or more boards."""
        # Round stats up to multiple of 30
        reps += 29
        reps -= reps % 30

        if len(c['daisy_chain']) != len(c['start_delay']):
            raise Exception('daisy_chain and start_delay must be same length.')

        if len(c['daisy_chain']):
            # run multiple boards, with first board as master
            devs = [self.getDevice(c, n) for n in c['daisy_chain']]
            delays = c['start_delay']
        else:
            # run the selected device only
            devs = [self.selectedDevice(c)]
            delays = [0]
        slaves = [i != 0 for i in range(len(devs))]
        devices = zip(devs, delays, slaves)

        devs[0].sendMemory(c['mem'], reps)

        # run boards in reverse order to ensure synchronization
        #print 'starting to run sequence.'
        start = datetime.now()
        attempts = [dev.runSequence(slave, delay, reps,
                                    getTimingData=getTimingData)
                    for dev, delay, slave in reversed(devices)]
        #print 'trying on boards:', self.daisy_chain
        results = yield defer.DeferredList(attempts)
        #print 'runtime:', datetime.now() - start
        #print 'all boards done.'
        okay = True
        switches = []
        failures = []
        for dev, (success, result) in zip(devs, results):
            if success:
                switches.append(result)
            else:
                print 'Board %d timed out.' % dev.board
                failures.append(dev.board)
                okay = False
        if not okay:
            raise Exception('Boards %s timed out.' % failures)
        if getTimingData: # send data back in daisy chain order
            #print list(reversed(switches))
            returnValue(list(reversed(switches)))

    @setting(42, 'Daisy Chain', boards=['*s'], returns=['*s'])
    def daisy_chain(self, c, boards=None):
        """Set or get daisy chain board order.

        Set this to an empty list to run the selected board only.
        """
        if boards is None:
            boards = c['daisy_chain']
        else:
            c['daisy_chain'] = boards
        return boards

    @setting(43, 'Start Delay', delays=['*w'], returns=['*w'])
    def start_delay(self, c, delays=None):
        """Set start delays in ns for SRAM in the daisy chain.

        Must be the same length as daisy_chain for sequence to execute.
        """
        if delays is None:
            delays = c['start_delay']
        else:
            c['start_delay'] = delays
        return delays


    @setting(50, 'Debug Output', data=['(wwww)'], returns=[''])
    def debug_output(self, c, data):
        """Outputs data directly to the output bus."""
        dev = self.selectedDevice(c)
        pkt = [2, 1] + [0]*11
        for d in data:
            pkt += [d & 0xFF,
                   (d >> 8) & 0xFF,
                   (d >> 16) & 0xFF,
                   (d >> 24) & 0xFF]
        pkt += [0]*16 + [0]*11
        yield dev.sendRegisters(pkt)


    @setting(51, 'Run SRAM', data=['*w'], loop=['b'], returns=['(ww)'])
    def run_sram(self, c, data, loop=False):
        """Loads data into the SRAM and executes.

        If loop is True, the sequence will be repeated forever,
        otherwise it will be executed just once.  Sending
        an empty list of data will clear the SRAM.
        """
        dev = self.selectedDevice(c)

        pkt = [0, 1] + [0]*54
        yield dev.sendRegisters(pkt)

        if not len(data):
            returnValue((0, 0))

        if loop:
            # make sure data is at least 20 words long by repeating it
            data *= (20-1)/len(data) + 1
            hdr = 3
        else:
            # make sure data is at least 20 words long by repeating first value
            data += [data[0]] * (20-len(data))
            hdr = 4
            
        dev.sramAddress = 0
        r = yield dev.sendSRAM(data)

        encode = lambda a: [a & 0xFF, (a>>8) & 0xFF, (a>>16) & 0xFF]
        pkt = [hdr, 0] + [0]*11 + encode(r[0]) + encode(r[1]-1) + [0]*37
        yield dev.sendRegistersNoReadback(pkt)
        returnValue(r)


    @setting(100, 'I2C', data=['*w'], returns=['*w'])
    def i2c(self, c, data):
        """Runs an I2C Sequence

        The entries in the WordList to be sent have the following meaning:
          0..255 : send this byte
          256:     read back one byte without acknowledging it
          257:     read back one byte with ACK
          258:     sent data and start new packet
        For each 256 or 257 entry in the WordList to be sent, the read-back byte is appended to the returned WordList.
        In other words: the length of the returned list is equal to the count of 256's and 257's in the sent list.
        """
        dev = self.selectedDevice(c)
        return dev.runI2C(data)


    @setting(110, 'LEDs', data=['w', '(bbbbbbbb)'], returns=['w'])
    def leds(self, c, data):
        """Sets the status of the 8 I2C LEDs."""
        dev = self.selectedDevice(c)

        if isinstance(data, tuple):
            # convert to a list of digits, and interpret as binary int
            data = long(''.join(str(int(b)) for b in data), 2)

        yield dev.runI2C([192 , 68, data & 255])  
        returnValue(data)


    @setting(120, 'Reset Phasor', returns=['b: phase detector output'])
    def reset_phasor(self, c):
        """Resets the clock phasor."""
        dev = self.selectedDevice(c)

        pkt = [152,   0, 127, 0, 258,  # set I to 0 deg
               152,  34, 254, 0, 258,  # set Q to 0 deg
               112,  65, 258,          # set enable bit high
               112, 193, 258,          # set reset high
               112,  65, 258,          # set reset low
               112,   1, 258,          # set enable low
               113, 256]               # read phase detector

        r = yield dev.runI2C(pkt)
        returnValue((r[0] & 1) > 0)


    @setting(121, 'Set Phasor',
                  data=[': poll phase detector only',
                        'v[rad]: set angle (in rad, deg, \xF8, \', or ")'],
                  returns=['b: phase detector output'])
    def set_phasor(self, c, data=None):
        """Sets the clock phasor angle and reads the phase detector bit."""
        dev = self.selectedDevice(c)

        if data is None:
            pkt = [112,  1, 258, 113, 256]
        else:
            sn = int(round(127 + 127*sin(data))) & 255
            cs = int(round(127 + 127*cos(data))) & 255
            pkt = [152,  0, sn, 0, 258,
                   152, 34, cs, 0, 258,
                   112,  1, 258, 113, 256]
                   
        r = yield dev.runI2C(pkt)
        returnValue((r[0] & 1) > 0)

    def getCommand(self, cmds, chan):
        """Get a command from a dictionary of commands.

        Raises a helpful error message if the given channel is not allowed.
        """
        try:
            return cmds[chan]
        except:
            raise Exception("Allowed channels are %s." % sorted(cmds.keys()))

    @setting(130, 'Vout', chan=['s'], V=['v[V]'], returns=['w'])
    def vout(self, c, chan, V):
        """Sets the output voltage of any Vout channel, A, B, C or D."""
        cmd = self.getCommand({'A': 16, 'B': 18, 'C': 20, 'D': 22}, chan)
        dev = self.selectedDevice(c)
        val = int(max(min(round(V*0x3333), 0x10000), 0))
        pkt = [154, cmd, (val >> 8) & 0xFF, val & 0xFF]
        yield dev.runI2C(pkt)
        returnValue(val)
        

    @setting(135, 'Ain', returns=['v[V]'])
    def ain(self, c):
        """Reads the voltage on Ain."""
        dev = self.selectedDevice(c)
        pkt = [144, 0, 258, 145, 257, 256]
        r = yield dev.runI2C(pkt)
        returnValue(T.Value(((r[0]<<8) + r[1])/819.0, 'V'))


# some helper methods

def bistChecksum(data):
    bist = [0, 0]
    for i in range(0, len(data), 2):
        for j in range(2):
            if data[i+j] & 0x3FFF != 0:
                bist[j] = (((bist[j] << 1) & 0xFFFFFFFE) | ((bist[j] >> 31) & 1)) ^ ((data[i+j] ^ 0x3FFF) & 0x3FFF)
    return bist

def boardMAC(board):
    """Get the MAC address of a board as a string."""
    return '00:01:CA:AA:00:' + ('0'+hex(int(board))[2:])[-2:].upper()

def listify(data):
    return data if isinstance(data, list) else [data]

def words2str(list):
    return array('B', list).tostring()

def sequenceTime(sequence):
    """Conservative estimate of the length of a sequence in seconds."""
    cycles = sum([cmdTime(c) for c in sequence])
    return cycles * 40e-9
    
def cmdTime(cmd):
    """A conservative estimate of the number of cycles a given command takes."""
    opcode = (cmd & 0xF00000) >> 20
    abcde  = (cmd & 0x0FFFFF)
    xy     = (cmd & 0x00FF00) >> 8
    ab     = (cmd & 0x0000FF)

    if opcode in [0x0, 0x1, 0x2, 0x4, 0x8, 0xA]:
        return 1
    if opcode == 0xF:
        return 2
    if opcode == 0x3:
        return abcde + 1 # delay
    if opcode == 0xC:
        return 250*8 # maximum SRAM length is 8us



__server__ = FPGAServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
