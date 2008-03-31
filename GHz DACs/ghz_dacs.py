#!c:\python25\python.exe

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

from labrad import types as T, util
from labrad.devices import DeviceWrapper, DeviceServer
from labrad.server import setting
from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

import struct

from array import array as py_array
from datetime import datetime, timedelta
from math import sin, cos

DEBUG = False

if DEBUG:
    import numpy


#NUMRETRIES = 1
SRAM_LEN = 8192
MEM_LEN = 256

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

        self.sram = '\x00' * (SRAM_LEN*4)
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
        pkt[13:15] = reps & 0xFF, (reps >> 8) & 0xFF
        pkt[43:45] = int(slave), int(delay)
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
        adr = startadr = 0 #(self.sramAddress + 255) & SRAM_LEN
        endadr = startadr + totallen
        p = self.server.packet()
        needToSend = False
        origdata = data
        if DEBUG:
            d = numpy.fromstring(data, dtype=int)
            print self.MAC
            da =  d & 0x00003FFF
            db = (d & 0x0FFFC000) >> 14
            da -= ((da & 8192)>>13)*16384
            db -= ((db & 8192)>>13)*16384
            for values in zip(db, da)[450:650]:
                print "%5d, %5d" % values
        while len(data) > 0:
            page, data = data[:1024], data[1024:]
            curpage = self.sram[adr:adr+len(page)]
            if True: #page != curpage:
                if len(page) < 1024:
                    page += '\x00'*(1024-len(page))
                pkt = chr((adr >> 10) & 31) + '\x00' + page
                p.write(pkt)
                adr += 1024
                needToSend = True
        if needToSend:
            yield p.send(context=self.ctx)
        self.sram=self.sram[0:startadr] + origdata + self.sram[endadr:]
        self.sramAddress = endadr
        returnValue((startadr/4, endadr/4))

    @inlineCallbacks
    def sendMemory(self, data):
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
                pkt = [(adr >> 8)] + \
                      [(n >> j) & 255 for n in page for j in (0, 8, 16)]
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

    @inlineCallbacks
    def runSerial(self, op, data):
        pkt = [0, 1] + [0]*54
        pkt[46:48] = self.DACclocks, op
        answer = []
        for d in listify(data):
            pkt[48:51] =  d & 255, (d>>8) & 255, (d>>16) & 255
            r = yield self.sendRegisters(pkt)
            answer.append(r[56])
            # print ['PLL: ', 'DAC A: ', 'DAC B: '][op-1] + hex(d) + ' = ' + hex(r[56])
        returnValue(answer)


class FPGAServer(DeviceServer):
    name = 'GHz DACs'
    deviceWrapper = FPGADevice

    #retryStats = [0] * NUMRETRIES

    # possible links: name, server, port
    possibleLinks = [('DR Lab', 'direct_ethernet', 1),
                     ('DR Lab', 'dr_direct_ethernet', 1),
                     ('ADR Lab', 'adr_direct_ethernet', 1)]

    @inlineCallbacks
    def initServer(self):
        yield DeviceServer.initServer(self)
        self.lock = defer.DeferredLock()

    def initContext(self, c):
        c['daisy_chain'] = []
        c['start_delay'] = []
        
    @inlineCallbacks
    def findDevices(self):
        cxn = self.client
        yield cxn.refresh()
        found = []
        for name, server, port in self.possibleLinks:
            if server not in cxn.servers:
                # server not found, remove all devices on this server
                names=self.devices.keys()
                for dname in names:
                    dev = self.devices[dname]
                    if dev.serverName == server:
                        del self.devices[dname]
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
            MAC = names[list(ports).index(port)][-17:]

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
        d = c.setdefault(dev, {})
        d['sramAddress'] = addr*4
        return addr
##        if addr is None:
##            addr = dev.sramAddress
##        else:
##            dev.sramAddress = addr
##        return long(addr)


    @setting(21, 'SRAM', data=['*w: SRAM Words to be written', 's: Raw SRAM data'],
                         returns=['(ww): Start address, Length'])
    def sram(self, c, data):
        """Writes data to the SRAM at the current starting address."""
        dev = self.selectedDevice(c)
        d = c.setdefault(dev, {})
        addr = d.setdefault('sramAddress', 0)
        if d.has_key('sram'):
            sram = d['sram']
        else:
            sram = '\x00' * (SRAM_LEN * 4)
        if isinstance(data, list):
            data = struct.pack('I'*len(data), *data)
        d['sram'] = sram[0:addr] + data + sram[addr+len(data):]
        d['sramAddress'] += len(data)
        return addr/4, len(data)/4


    @setting(31, 'Memory', data=['*w: Memory Words to be written'],
                           returns=['(ww): Start address, Length'])
    def memory(self, c, data):
        """Writes data to the Memory at the current starting address."""
        dev = self.selectedDevice(c)
        d = c.setdefault(dev, {})
        d['mem'] = data
        return 0, len(data)
        #return dev.sendMemory(data)


    @setting(40, 'Run Sequence', reps=['w'], getTimingData=['b'],
                                 setuppkts=['*((ww){context}, s{server}, *(s{setting}, ?{data}))'],
                                 returns=['*2w'])
    def run_sequence(self, c, reps=30, getTimingData=True, setuppkts=None):
        """Executes a sequence on one or more boards."""
        # Round stats up to multiple of 30
        reps += 29
        reps -= reps % 30

        #print 'hi2'
        if len(c['daisy_chain']) != len(c['start_delay']):
            print 'bad.'
            raise Exception('daisy_chain and start_delay must be same length.')
        #print 'good'

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

        # run boards in reverse order to ensure synchronization
        #print 'starting to run sequence.'
        #start = datetime.now()
        @inlineCallbacks
        def updateDev(dev):
            if dev in c:
                if 'mem' in c[dev]:
                    yield dev.sendMemory(c[dev]['mem'])
                if 'sram' in c[dev]:
                    #dev.sramAddress = 0
                    yield dev.sendSRAM(c[dev]['sram'])

        setupReqs = []
        if setuppkts is not None:
            for spCtxt, spServer, spSettings in setuppkts:
                if spCtxt[0] == 0:
                    print "Using a context with high ID = 0 for packet requests might not do what you want!!!"
                p = self.client[spServer].packet(context=spCtxt)
                for spSetting, spData in spSettings:
                    p[spSetting](spData)
                setupReqs.append(p)

                    
        ## begin critical section
        try:
            yield self.lock.acquire()
        
            # send setup packets
            if len(setupReqs) > 0:
                setups = [p.send() for p in setupReqs]
                r = yield defer.DeferredList(setups)
                if not all(success for success, result in r):
                    raise Exception('Error while sending setup packets!')
        
            # send memory and SRAM content
            updates = [updateDev(dev) for dev in reversed(devs)]
            r = yield defer.DeferredList(updates)
            if not all(success for success, result in r):
                raise Exception('Failed to update MEM and/or SRAM!')
        
            # run all boards
            attempts = [dev.runSequence(slave, delay, reps,
                                        getTimingData=getTimingData)
                        for dev, delay, slave in reversed(devices)]
            results = yield defer.DeferredList(attempts)
        finally:
            # release lock at end, even (especially!) if an error happened
            self.lock.release()
        ## end critical section

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
            returnValue(list(reversed(switches)))

##    @setting(41, 'Retry Stats', returns=['*w'])
##	def retry_stats(self, c):
##		"""Returns a list indicating the number of retries.
##
##		The nth element of the list (starting from 0) indicates the
##		number of runs with n retries.
##		"""
##		return self.retryStats

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
            
        data = struct.pack('I'*len(data), *data)
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

        yield dev.runI2C([200 , 68, data & 255])  # 192 for build 1
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


    @setting(200, 'PLL', data=['w', '*w'], returns=['*w'])
    def pll(self, c, data):
        """Sends a command or a sequence of commands to the PLL

        The returned WordList contains any read-back values.
        It has the same length as the sent list.
        """
        dev = self.selectedDevice(c)
        return dev.runSerial(1, data)

    @setting(204, 'DAC', chan=['s'], data=['w', '*w'], returns=['*w'])
    def dac_cmd(self, c, chan, data):
        """Send a command or sequence of commands to either DAC.

        The DAC channel must be either 'A' or 'B'.
        The returned list of words contains any read-back values.
        It has the same length as the sent list.
        """
        cmd = self.getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDevice(c)
        return dev.runSerial(cmd, data)


    @setting(206, 'DAC Clock Polarity', chan=['s'], invert=['b'], returns=['b'])
    def dac_pol(self, c, chan, invert):
        """Sets the clock polarity for either DAC.

        This command does not immediately update the clock polarity.
        Another command that sends a packet is needed.
        """
        cmds = self.getCommand({'A': (0x10, 0x11), 'B': (0x20, 0x22)}, chan)
        dev = self.selectedDevice(c)
        pkt = [0, 1] + [0]*54
        pkt[46] = cmds[invert]
        yield dev.sendRegisters(pkt)
        returnValue(invert)


    @setting(210, 'PLL Init', returns=[''])
    def init_pll(self, c, data):
        """Sends the initialization sequence to the PLL.

        The sequence is [0x1FC093, 0x1FC092, 0x100004, 0x000C11]."""
        dev = self.selectedDevice(c)
        yield dev.runSerial(1, [0x1fc093, 0x1fc092, 0x100004, 0x000c11])
        pkt = [4, 0] + [0]*54
        yield dev.sendRegistersNoReadback(pkt)


    @setting(211, 'PLL Reset', returns=[''])
    def pll_reset(self, c):
        """Resets the FPGA internal GHz serializer PLLs
        """
        dev = self.selectedDevice(c)
        pkt = [0,1] + [0]*54
        pkt[46] = 0x80

        yield dev.sendRegisters(pkt)

    @setting(212, 'PLL Query', returns=['b'])
    def pll_query(self, c):
        """Checks the FPGA internal GHz serializer PLLs for lock failures.
        Returns T if any of the PLLs have lost lock since the last reset.
        """
        dev = self.selectedDevice(c)
        pkt = [0,1] + [0]*54

        r = yield dev.sendRegisters(pkt)

        returnValue((r[58] & 0x80)>0)


    @setting(220, 'DAC Init', chan=['s'], signed=['b'], returns=['b'])
    def init_dac(self, c, chan, signed=False):
        """Sends an initialization sequence to either DAC.
        
        For unsigned data, this sequence is 0026, 0006, 1603, 0500
        For signed data, this sequence is 0024, 0004, 1603, 0500
        """
        cmd = self.getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDevice(c)
        pkt = [0x0024, 0x0004, 0x1603, 0x0500] if signed else \
              [0x0026, 0x0006, 0x1603, 0x0500]
        yield dev.runSerial(cmd, pkt)
        returnValue(signed)


    @setting(221, 'DAC LVDS', chan=['s'], data=['w'], returns=['(www*(bb))'])
    def dac_lvds(self, c, chan, data=None):
        """Set or determine DAC LVDS phase shift and return y, z check data."""
        cmd = self.getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDevice(c)
        pkt = [[0x0400 + (i<<4), 0x8500, 0x0400 + i, 0x8500][j]
               for i in range(16) for j in range(4)]

        if data is None:
            answer = yield dev.runSerial(cmd, [0x0500] + pkt)
            answer = [answer[i*2+2] & 1 for i in range(32)]

            MSD = -2
            MHD = -2

            for i in range(16):
                if MSD == -2 and answer[i*2] == 1:
                    MSD = -1
                if MSD == -1 and answer[i*2] == 0:
                    MSD = i
                if MHD == -2 and answer[i*2+1] == 1:
                    MHD = -1
                if MHD == -1 and answer[i*2+1] == 0:
                    MHD = i

            MSD = max(MSD, 0)
            MHD = max(MHD, 0)
            t = (MHD-MSD)/2 & 15
        else:
            MSD = 0
            MHD = 0
            t = data & 15

        answer = yield dev.runSerial(cmd, [0x0500 + (t<<4)] + pkt)
        answer = [(bool(answer[i*4+2] & 1), bool(answer[i*4+4] & 1))
                  for i in range(16)]
        returnValue((MSD, MHD, t, answer))


    @setting(222, 'DAC FIFO', chan=['s'], returns=['(wwbww)'])
    def dac_fifo(self, c, chan):
        """Moves the LVDS into a region where the FIFO counter is stable,
        adjusts the clock polarity and phase offset to make FIFO counter = 3,
        and finally returns LVDS setting back to original value
        """
        op = self.getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDevice(c)

        # set clock polarity to positive
        clkinv = False
        yield self.dac_pol(c, chan, clkinv)

        pkt = [0x0500, 0x8700] # set LVDS delay and read FIFO counter
        reading = yield dev.runSerial(op, [0x8500] + pkt) # read current LVDS delay and exec pkt
        oldlvds = (reading[0] & 0xF0) | 0x0500 # grab current LVDS setting
        reading = reading[2] # get FIFO counter reading
        base = reading
        while reading == base: # until we have a clock edge ...
            pkt[0] += 16 # ... move LVDS
            reading = (yield dev.runSerial(op, pkt))[1]

        pkt = [pkt[0] + 16*i for i in [2, 4]] # slowly step 6 clicks beyond edge to be centered on bit
        newlvds = pkt[-1]
        yield dev.runSerial(op, pkt)

        tries = 5
        found = False

        while tries > 0 and not found:
            tries -= 1
            pkt =  [0x0700, 0x8700, 0x0701, 0x8700, 0x0702, 0x8700, 0x0703, 0x8700]
            reading = yield dev.runSerial(op, pkt)
            reading = [(reading[i]>>4) & 15 for i in [1, 3, 5, 7]]
            try:
                PHOF = reading.index(3)
                pkt = [0x0700 + PHOF, 0x8700]
                reading = long(((yield dev.runSerial(op, pkt))[1] >> 4) & 7)
                found = True
            except:
                clkinv = not clkinv
                yield self.dac_pol(c, chan, clkinv)

        if not found:
            raise Exception('Cannot find a FIFO offset to get a counter value of 3! Found: '+repr(reading))

        # return to old lvds setting
        pkt = range(newlvds, oldlvds, -32)[1:] + [oldlvds]
        yield dev.runSerial(op, pkt)
        ans = (oldlvds >> 4) & 15, (newlvds >> 4) & 15, clkinv, PHOF, reading
        returnValue(ans)


    @setting(223, 'DAC Cross Controller',
                  chan=['s'], delay=['i'], returns=['i'])
    def dac_xctrl(self, c, chan, delay=0):
        """Sets the cross controller delay on either DAC

        Range for delay is -63 to 63.
        """
        dev = self.selectedDevice(c)
        cmd = self.getCommand({'A': 2, 'B': 3}, chan)
        if delay < -63 or delay > 63:
            raise T.Error(11, 'Delay must be between -63 and 63')

        seq = [0x0A00, 0x0B00 - delay] if delay < 0 else \
              [0x0A00 + delay, 0x0B00]
        yield dev.runSerial(cmd, seq)
        returnValue(delay)


    @setting(225, 'DAC BIST', chan=['s'], data=['*w'],
                              returns=['(b(ww)(ww)(ww))'])
    def dac_bist(self, c, chan, data):
        """Run a BIST on the given SRAM sequence."""
        cmd, shift = self.getCommand({'A': (2, 0), 'B': (3, 14)}, chan)
        dev = self.selectedDevice(c)
        pkt = [4, 0] + [0]*54
        yield dev.sendRegistersNoReadback(pkt)

        dat = [d & 0x3FFF for d in data]
        data = [0, 0, 0, 0] + [d << shift for d in dat]
        # make sure data is at least 20 words long by appending 0's
        data += [0] * (20-len(data))
        dev.sramAddress = 0
        data = struct.pack('I'*len(data), *data)
        r = yield dev.sendSRAM(data)
        yield dev.runSerial(cmd, [0x0004, 0x1107, 0x1106])

        encode = lambda a: [a & 0xFF, (a>>8) & 0xFF, (a>>16) & 0xFF]
        pkt = [4, 0] + [0]*11 + encode(r[0]) + encode(r[1]-1) + [0]*37
        yield dev.sendRegistersNoReadback(pkt)

        seq = [0x1126, 0x9200, 0x9300, 0x9400, 0x9500,
               0x1166, 0x9200, 0x9300, 0x9400, 0x9500,
               0x11A6, 0x9200, 0x9300, 0x9400, 0x9500,
               0x11E6, 0x9200, 0x9300, 0x9400, 0x9500]
        theory = tuple(bistChecksum(dat))
        bist = yield dev.runSerial(cmd, seq)
        reading = [(bist[i+4] <<  0) + (bist[i+3] <<  8) + \
                   (bist[i+2] << 16) + (bist[i+1] << 24) \
                   for i in [0, 5, 10, 15]]
        lvds, fifo = tuple(reading[0:2]), tuple(reading[2:4])

        # lvds and fifo may be reversed.  This is okay
        if tuple(reversed(lvds)) == theory:
            lvds = tuple(reversed(lvds))
        if tuple(reversed(fifo)) == theory:
            fifo = tuple(reversed(fifo))
        returnValue((lvds == theory and fifo == theory, theory, lvds, fifo))


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
    return py_array('B', list).tostring()

def sequenceTime(sequence):
    """Conservative estimate of the length of a sequence in seconds."""
    cycles = sum(cmdTime(c) for c in sequence)
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
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
