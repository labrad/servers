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
import time

import numpy

DEBUG = False

NUM_PAGES = 2

SRAM_LEN = 8192
SRAM_PAGE_LEN = 4096

MEM_LEN = 512
MEM_PAGE_LEN = 256

TIMING_PACKET_LEN = 30

TIMEOUT_FACTOR = 10

# TODO: make sure paged operations (datataking) don't conflict with e.g. bringup
# TODO: factor out register packet creation into separate functions
# TODO: store memory and SRAM as numpy arrays, rather than lists and strings, respectively
# TODO: update stored versions of memory and SRAM only when a write happens (not when write is requested)
     
class TimedLock(object):
    """
    A lock that times how long it takes to acquire.
    """

    TIMES_TO_KEEP = 100
    locked = 0

    def __init__(self):
        self.waiting = []

    @property
    def times(self):
        if not hasattr(self, '_times'):
            self._times = []
        return self._times

    def addTime(self, dt):
        times = self.times
        times.append(dt)
        if len(times) > self.TIMES_TO_KEEP:
            times.pop(0)

    def meanTime(self):
        times = self.times
        if not len(times):
            return 0
        return sum(times) / len(times)

    def acquire(self):
        """Attempt to acquire the lock.

        @return: a Deferred which fires on lock acquisition.
        """
        d = defer.Deferred()
        if self.locked:
            t = time.time()
            self.waiting.append((d, t))
        else:
            self.locked = 1
            self.addTime(0)
            d.callback(0)
        return d

    def release(self):
        """Release the lock.

        Should be called by whomever did the acquire() when the shared
        resource is free.
        """
        assert self.locked, "Tried to release an unlocked lock"
        self.locked = 0
        if self.waiting:
            # someone is waiting to acquire lock
            self.locked = 1
            d, t = self.waiting.pop(0)
            dt = time.time() - t
            self.addTime(dt)
            d.callback(dt)

class FPGADevice(DeviceWrapper):
    """Manages communication with a single GHz DAC board.

    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @inlineCallbacks
    def connect(self, de, port, board, build, name):
        """Establish a connection to the board."""
        print 'connecting to: %s (build #%d)' % (boardMAC(board), build)

        self.server = de
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = boardMAC(board)
        self.devName = name
        self.serverName = de._labrad_name

        self.sram = '\x00' * (SRAM_LEN*4)
        self.mem = [0L] * MEM_LEN
        self.DACclocks = 0
        self.timeout = T.Value(1, 's')

        # set up our context with the ethernet server
        p = self.makePacket()
        p.connect(port)
        p.require_length(70)
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()

    def makePacket(self):
        """Create a new packet to be sent to the ethernet server for this device."""
        return self.server.packet(context=self.ctx)

    def makeSRAM(self, data, p, page=0):
        """Update a packet for the ethernet server with SRAM commands."""
        totallen = len(data)
        adr = startadr = page * SRAM_PAGE_LEN * 4
        endadr = startadr + totallen
        needToSend = False
        origdata = data
        while len(data) > 0:
            page, data = data[:1024], data[1024:]
            curpage = self.sram[adr:adr+len(page)]
            #if page != curpage: # only upload changes
            if True: # upload entire SRAM to ensure pipeline correctness
                if len(page) < 1024:
                    #newpage = numpy.zeros(256, dtype='uint32')
                    #newpage[:len(page)] = page
                    #page = newpage
                    page += '\x00' * (1024-len(page))
                pkt = chr((adr >> 10) & 31) + '\x00' + page
                p.write(pkt)
                adr += 1024
                needToSend = True
        self.sram = self.sram[:startadr] + origdata + self.sram[endadr:]
        return needToSend, (startadr/4, endadr/4)

    def makeMemory(self, data, p, page=0):
        """Update a packet for the ethernet server with Memory commands."""

        if len(data) > MEM_PAGE_LEN:
            msg = "Memory length %d exceeds maximum memory length %d (one page)."
            raise Exception(msg % (len(data), MEM_PAGE_LEN))
        # translate SRAM addresses for higher pages
        if page:
            shiftSRAM(data, page)
        
        totallen = len(data)
        adr = startadr = page * MEM_PAGE_LEN
        endadr = startadr + totallen
        current = self.mem[startadr:endadr]
        needToSend = (data != current)
        #if needToSend: # only send if the MEM is new
        if True: # always send mem to ensure pipeline correctness
            while len(data) > 0:
                page, data = data[:MEM_PAGE_LEN], data[MEM_PAGE_LEN:]
                if len(page) < MEM_PAGE_LEN:
                    page += [0] * (MEM_PAGE_LEN - len(page))
                # TODO: use numpy here
                pkt = [(adr >> 8)] + \
                      [(n >> j) & 255 for n in page for j in (0, 8, 16)]
                p.write(words2str(pkt))
                adr += MEM_PAGE_LEN
            self.mem[startadr:endadr] = data
        return needToSend, (startadr, endadr)

    def load(self, mem=None, sram=None, page=0):
        """Create a packet to write Memory and SRAM data to the FPGA."""
        p = self.makePacket()
        if mem is not None:
            self.makeMemory(mem, p, page=page)
        if sram is not None:
            self.makeSRAM(sram, p, page=page)
        return p
    
    def collect(self, nPackets, timeout, triggerCtx, devCtxs):
        """Create a packet to collect data on the FPGA."""
        p = self.makePacket()
        p.timeout(T.Value(timeout, 's'))
        p.collect(nPackets)
        # send a packet to the trigger to indicate that we're done
        p.send_trigger(triggerCtx)
        for ctx in devCtxs:
            p.send_trigger(ctx)
        p.wait_for_trigger(len(devCtxs))
        return p
    
    def read(self, nPackets):
        """Create a packet to readback data from the FPGA."""
        p = self.makePacket()
        p.read(nPackets)
        return p
            
    def discard(self, nPackets):
        """Create a packet to discard data on the FPGA."""
        p = self.makePacket()
        p.discard(nPackets)
        return p

    def clear(self, triggerCtx=None, devCtxs=[]):
        """Create a packet to clear the ethernet buffer for this board."""
        p = self.makePacket()
        p.clear()
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        for ctx in devCtxs:
            p.send_trigger(ctx)
        p.wait_for_trigger(len(devCtxs))
        return p

    @inlineCallbacks
    def sendSRAM(self, data):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        needToSend, result = self.makeSRAM(data, p)
        if needToSend:
            yield p.send()
        returnValue(result)

    @inlineCallbacks
    def sendMemory(self, data):
        """Write Memory data to the FPGA."""
        p = self.makePacket()
        needToSend, result = self.makeMemory(data, p)
        if needToSend:
            yield p.send()
        returnValue(result)

    @inlineCallbacks
    def sendMemoryAndSRAM(self, mem, sram):
        """Write both Memory and SRAM data to the FPGA."""
        p = self.makePacket()
        sendMem, resultMem = self.makeMemory(mem, p)
        sendSRAM, resultSRAM = self.makeSRAM(sram, p)
        if sendMem or sendSRAM:
            yield p.send()
        returnValue((resultMem, resultSRAM))

    @inlineCallbacks
    def sendRegisters(self, regs, readback=True):
        """Send a register packet and optionally readback the result.

        If readback is True, the result packet is returned as a string of bytes.
        """
        regs[45] = 249 # Start on us boundary
        if isinstance(regs, numpy.ndarray):
            data = regs.tostring()
        else:
            data = words2str(regs)
        p = self.makePacket()
        p.write(data)
        if readback:
            p.read()
        ans = yield p.send()
        if readback:
            src, dst, eth, data = ans.read
            returnValue(data)

    @inlineCallbacks
    def runI2C(self, data):
        """Run a list of I2C commands on the board."""
        regs = numpy.zeros(56, dtype='uint8')
        regs[0:2] = 0, 2

        answer = []
        while data[0] == 258:
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
                    regs[12-i] = data[i]
                else:
                    regs[12-i] = 0
                cur >>= 1

            regs[2:5] = stopI2C, readwriteI2C, ackI2C

            r = yield self.sendRegisters(regs)

            for i in range(cnt):
                if data[i] in [256, 257]:
                    answer += [ord(r[61+cnt-i])]

            data = data[cnt:]
            while data[0] == 258:
                data = data[1:]

        returnValue(answer)

    @inlineCallbacks
    def runSerial(self, op, data):
        """Run a command or list of commands through the serial interface."""
        regs = numpy.zeros(56, dtype='uint8')
        regs[0:2] = 0, 1
        regs[46:48] = self.DACclocks, op
        answer = []
        for d in listify(data):
            regs[48:51] =  d & 255, (d>>8) & 255, (d>>16) & 255
            r = yield self.sendRegisters(regs)
            answer.append(ord(r[56]))
        returnValue(answer)


class BoardGroup(object):
    """Manages a group of GHz DAC boards that can be run simultaneously.
    
    All the servers must be daisy-chained to allow for synchronization,
    and also must be connected to the same network card.  Currently, one
    board group is created automatically for each detected network card.
    Only one sequence at a time can be run on a board group, but memory
    and SRAM updates can be pipelined so that while a sequence is running
    on some set of the boards in the group, new sequence data for the next
    point can be uploaded.
    """
    def __init__(self, server, port):
        self._nextPage = 0
        Lock = TimedLock #defer.DeferredLock
        self.pageLocks = [Lock() for _ in range(NUM_PAGES)]
        self.runLock = Lock()
        self.readLock = Lock()
        self.server = server
        self.port = port
        self.ctx = server.context()
        self.setupState = set()
        self.runWaitTimes = []
        self.prevTriggers = 0
    
    @inlineCallbacks
    def init(self):
        """Set up the direct ethernet server in our own context."""
        p = self.server.packet(context=self.ctx)
        p.connect(self.port)
        yield p.send()
    
    def nextPage(self):
        """Get the next page to use for memory and SRAM upload."""
        page = self._nextPage
        self._nextPage = (self._nextPage + 1) % NUM_PAGES
        return page

    def makeRunPackets(self, data):
        """Create a function to make run packets.
        
        This allows us to do most of the work in advance,
        only leaving the final packet creation for the last
        moment, when we know how many triggers to expect
        from the previous run.
        """
        wait = self.server.packet(context=self.ctx)
        run = self.server.packet(context=self.ctx)
        both = self.server.packet(context=self.ctx)
        # wait for triggers and discard them
        wait.wait_for_trigger(0, key='nTriggers')
        both.wait_for_trigger(0, key='nTriggers')
        # run all boards
        for MAC, bytes in data:
            run.destination_mac(MAC)
            run.write(bytes)
            both.destination_mac(MAC)
            both.write(bytes)
        return wait, run, both

    def makeClearPackets(self, devs, collectResults):
        """Create packets to recover from a timeout error.
        
        For boards whose collect succeeded, we just clear the
        packet buffer.  For boards whose collect failed, we clear
        the buffer and resend the trigger to synchronize the start
        of the next run command.
        """
        devCtxs = [d[0].ctx for d in devs]
        clearPkts = [d[0].clear(None if s else self.ctx, devCtxs)
                     for d, (s, r) in zip(devs, collectResults)]
        msg = 'Some boards failed:\n'
        for d, (s, r) in zip(devs, collectResults):
            msg += d[0].devName
            if s:
                msg += ': OK\n\n'
            else:
                msg += ': timeout!\n' + r.getBriefTraceback() + '\n\n'
        return clearPkts, msg

    def makePackets(self, devs, timingOrder, page, reps, sync=249):
        """Make packets to run a sequence on this board group.

        Running a sequence has 4 stages:
        - Load memory and SRAM into all boards in parallel
          if possible, this is done in the background using a separate
          page while another sequence is running.  We load in reverse
          order, just to ensure that all loads are done before starting.

        - Run sequence by firing a single packet that starts all boards
          We start the master last, to ensure synchronization

        - Collect timing data to ensure that the sequence is finished
          We instruct the direct ethernet server to collect the packets
          but not send them yet.  Once collected, we can immediately run the
          next sequence if one was uploaded into the next page.

        - Read timing data
          Having started the next sequence (if one was waiting) we now
          read the timing data collected by the direct ethernet server,
          process it and return it.

        This function prepares the LabRAD packets that will be sent for
        each of these steps, but does not actually send anything.
        """
        # TODO: preflatten packets to reduce the send time
        
        # load memory and SRAM
        loadPkts = [dev.load(mem, sram, page)
                    for dev, mem, sram, slave, delay in devs]

        # run all boards
        regs = numpy.zeros(56, dtype='uint8')
        regs[0:2] = 1 + 128*page, 3
        regs[13:15] = reps & 0xFF, (reps >> 8) & 0xFF
        regs[45] = sync # start on us boundary
        data = []
        for dev, mem, sram, slave, delay in reversed(devs): # run master last
            regs[43:45] = int(slave), int(delay)
            data.append((dev.MAC, regs.tostring()))
        runPkts = self.makeRunPackets(data)
        
        # collect and read (or discard) timing results
        collectPkts = []
        readPkts = []
        devCtxs = [d[0].ctx for d in devs]
        for dev, mem, sram, slave, delay in devs:
            nTimers = timerCount(mem)
            N = reps * nTimers / TIMING_PACKET_LEN
            seqTime = TIMEOUT_FACTOR * (sequenceTime(mem) * reps + 1)
            collectPkts.append(dev.collect(N, seqTime, self.ctx, devCtxs))
            if timingOrder is None or dev.devName in timingOrder:
                readPkts.append(dev.read(N))
            else:
                readPkts.append(dev.discard(N))

        return loadPkts, runPkts, collectPkts, readPkts

    @inlineCallbacks
    def sendAll(self, packets, info, infoList=None):
        """Send a list of packets and wrap them up in a deferred list."""
        results = yield defer.DeferredList([p.send() for p in packets])
        if all(s for s, r in results):
            # return the list of results
            returnValue([r for s, r in results])
        else:
            # create an informative error message
            msg = 'Error(s) occured during %s:\n' % info
            if infoList is None:
                msg += ''.join(r.getBriefTraceback() for s, r in results if not s)
            else:
                for i, (s, r) in zip(infoList, results):
                    if s:
                        msg += str(i) + ': OK\n\n'
                    else:
                        msg += str(i) + ': error!\n' + r.getBriefTraceback() + '\n\n'
            raise Exception(msg)
        
    def extractTiming(self, result):
        """Extract timing data coming back from a readPacket."""
        data = ''.join(data[3:63] for src, dst, eth, data in result.read)
        bytes = numpy.fromstring(data, dtype='uint8')
        timing = bytes[::2] + (bytes[1::2].astype('uint32') << 8)
        return timing

    @inlineCallbacks
    def run(self, devs, reps, setupPkts, getTimingData, timingOrder, sync, setupState):
        """Run a sequence on this board group."""
        if not all((d[0].serverName == self.server._labrad_name) and \
                   (d[0].port == self.port) for d in devs):
            raise Exception('All boards must belong to the same board group!')
        boardOrder = [d[0].devName for d in devs]
        
        # check whether this sequence will fit in just one page
        pageable = all(maxSRAM(mem) <= SRAM_PAGE_LEN
                       for dev, mem, sram, slave, delay in devs)
        if pageable:
            # run on just a single page
            page = self.nextPage()
            pageLocks = [self.pageLocks[page]]
            # shorten SRAM to at most one page
            devs = [(dev, mem, sram if sram is None else sram[:SRAM_PAGE_LEN*4], slave, delay)
                    for dev, mem, sram, slave, delay in devs]
        else:
            # start on page 0 and lock all pages
            print 'Paging off: SRAM too long.'
            page = 0
            pageLocks = self.pageLocks
        runLock = self.runLock
        readLock = self.readLock
        sendAll = self.sendAll
        
        # prepare packets
        loadPkts, runPkts, collectPkts, readPkts = \
                  self.makePackets(devs, timingOrder, page, reps, sync)
        
        try:
            for pageLock in pageLocks:
                yield pageLock.acquire()

            # stage 1: load
            sendDone = sendAll(loadPkts, "Load", boardOrder)
            runNow = runLock.acquire() # get in line for the runlock
            
            # stage 2: run
            try:
                yield sendDone
                yield runNow # now acquire the run lock
                needSetup = (not setupState) or (not self.setupState) or (not (setupState <= self.setupState))
                waitPkt, runPkt, bothPkt = runPkts
                waitPkt['nTriggers'] = self.prevTriggers
                bothPkt['nTriggers'] = self.prevTriggers
                self.prevTriggers = len(devs) # set the number of triggers for the next point to wait for
                if needSetup:
                    r = yield waitPkt.send() # if this fails, something BAD happened!
                    try:
                        yield sendAll(setupPkts, "Setup")
                        self.setupState = setupState
                    except:
                        # if there was an error, clear setup state
                        self.setupState = set()
                        raise
                    yield runPkt.send()
                else:
                    r = yield bothPkt.send() # if this fails, something BAD happened!
                
                # keep track of how long the packet waited before being able to run
                self.runWaitTimes.append(float(r['nTriggers']))
                if len(self.runWaitTimes) > 100:
                    self.runWaitTimes.pop(0)
                    
                yield readLock.acquire() # make sure we are next in line to read
               
                # send our collect packets and then release the run lock
                collectAll = defer.DeferredList([p.send() for p in collectPkts])
            finally:
                runLock.release()
            
            # wait for the collect packet
            results = yield collectAll
        finally:
            for pageLock in reversed(pageLocks):
                pageLock.release()
                
        #yield readNow # wait until all previous reads have been sent
        if all(s for s, r in results):
            readAll = sendAll(readPkts, "Read", boardOrder)
            readLock.release()
        else:
            # recover from timeout
            clearPkts, msg = self.makeClearPackets(devs, results)
            try:
                yield sendAll(clearPkts, "Timeout Recovery", boardOrder)
            finally:
                # if an error happens here, we are in trouble
                # but make sure to release read lock anyway
                readLock.release()
            raise Exception(msg)
        results = yield readAll # wait for read to complete

        if getTimingData:
            if timingOrder is not None:
                results = [results[boardOrder.index(b)] for b in timingOrder]
            timing = numpy.vstack(self.extractTiming(r) for r in results)
            returnValue(timing)
    

class FPGAServer(DeviceServer):
    name = 'GHz DACs'
    deviceWrapper = FPGADevice

    # possible links: name, server, port
    possibleLinks = [('DR Lab', 'DR Direct Ethernet', 1),
                     ('ADR Lab', 'ADR Direct Ethernet', 1)]

    @inlineCallbacks
    def initServer(self):
        self.boardGroups = {}
        yield DeviceServer.initServer(self)

    def initContext(self, c):
        c['daisy_chain'] = []
        c['start_delay'] = []
        c['timing_order'] = None
        c['master_sync'] = 249
        
    @inlineCallbacks
    def findDevices(self):
        print 'Refreshing...'
        cxn = self.client
        yield cxn.refresh()
        found = []
        for name, server, port in self.possibleLinks:
            if server not in cxn.servers:
                # server not found, remove all devices on this server
                names = self.devices.keys()
                for dname in names:
                    dev = self.devices[dname]
                    if dev.serverName == server:
                        print 'Removing device %s' % dev.devName
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

            # create board group for this link
            if (server, port) not in self.boardGroups:
                print 'Making board group:', (server, port)
                bg = self.boardGroups[server, port] = BoardGroup(de, port)
            else:
                bg = self.boardGroups[server, port]
            yield bg.init()

            # make a list of the boards currently known
            skips = {}
            for dname in self.devices:
                dev = self.devices[dname]
                if dev.serverName == de._labrad_name and dev.port == port:
                    skips[dev.board] = dev
            print 'Skipping:', sorted(skips.keys())

            p = de.packet()
            p.connect(port)
            p.require_length(70)
            p.timeout(T.Value(1, 's'))
            p.listen()

            # ping all boards
            for i in xrange(256):
                if i in skips:
                    found.append(skips[i].name)
                else:
                    p.destination_mac(boardMAC(i))
                    p.write(words2str([0, 1] + [0]*43 + [249] + [0]*10))
            yield p.send(context=ctx)

            # get ID packets from all boards
            while True:
                try:
                    ans = yield de.read(context=ctx)
                    src, dst, eth, data = ans
                    board, build = int(src[-2:], 16), ord(data[51])
                    devName = '%s FPGA %d' % (name, board)
                    args = de, port, board, build, devName
                    found.append((devName, args))
                except T.Error:
                    break

            # expire this context to stop listening
            yield cxn.manager.expire_context(de.ID, context=ctx)
        returnValue(found)


    @setting(20, 'SRAM Address', addr='w', returns='w')
    def sram_address(self, c, addr=None):
        """Sets the next SRAM address to be written to by SRAM."""
        dev = self.selectedDevice(c)
        d = c.setdefault(dev, {})
        d['sramAddress'] = addr*4
        return addr


    @setting(21, 'SRAM', data=['*w: SRAM Words to be written', 's: Raw SRAM data'],
                         returns='(ww): Start address, Length')
    def sram(self, c, data):
        """Writes data to the SRAM at the current starting address."""
        dev = self.selectedDevice(c)
        d = c.setdefault(dev, {})
        addr = d.setdefault('sramAddress', 0)
        if 'sram' in d:
            sram = d['sram']
        else:
            sram = '\x00' * addr
        if not isinstance(data, str):
            data = data.asarray.tostring()
        #if isinstance(data, list):
        #    data = struct.pack('I'*len(data), *data)
        d['sram'] = sram[0:addr] + data + sram[addr+len(data):]
        d['sramAddress'] += len(data)
        return addr/4, len(data)/4


    @setting(31, 'Memory', data='*w: Memory Words to be written',
                           returns='(ww): Start address, Length')
    def memory(self, c, data):
        """Writes data to the Memory at the current starting address."""
        dev = self.selectedDevice(c)
        d = c.setdefault(dev, {})
        d['mem'] = data
        return 0, len(data)


    @setting(40, 'Run Sequence', reps='w', getTimingData='b',
                                 setupPkts='*((ww){context}, s{server}, ?{((s?)(s?)(s?)...)})',
                                 setupState='*s',
                                 returns=['*2w', ''])
    def run_sequence(self, c, reps=30, getTimingData=True, setupPkts=[], setupState=[]):
        """Executes a sequence on one or more boards.

        reps:
            specifies the number of repetitions ('stats') to perform
            (rounded up to the nearest multiple of 30).

        getTimingData:
            specifies whether timing data should be returned.
            the timing data will be returned for those boards
            specified by the "Timing Order" setting, and in
            the order specified there as well.

        setupPkts:
            specifies packets to be sent to other servers before this
            sequence is run, e.g. to set the microwave frequency.
            
        setupState:
            a list of strings describing the setup state for this point.
            if this matches the last setup state used (up to reordering),
            the setup packets will not be sent for this point.  For example,
            the setupState might describe the amplitude and frequency of
            the various microwave sources for this sequence.
        """
        # Round stats up to multiple of the timing packet length
        reps += TIMING_PACKET_LEN - 1
        reps -= reps % TIMING_PACKET_LEN

        if len(c['daisy_chain']) != len(c['start_delay']):
            print 'daisy_chain and start_delay lengths do not match.'
            raise Exception('daisy_chain and start_delay must be same length.')
        
        if len(c['daisy_chain']):
            # run multiple boards, with first board as master
            devs = [self.getDevice(c, n) for n in c['daisy_chain']]
            delays = c['start_delay']
        else:
            # run the selected device only
            devs = [self.selectedDevice(c)]
            delays = [0]
        mems = [c.get(dev, {}).get('mem', None) for dev in devs]
        srams = [c.get(dev, {}).get('sram', None) for dev in devs]
        slaves = [i != 0 for i in range(len(devs))]
        devices = zip(devs, mems, srams, slaves, delays)
        if getTimingData:
            if c['timing_order'] is None:
                timingOrder = [d.devName for d in devs]
            else:
                timingOrder = c['timing_order']
        else:
            timingOrder = []

        setupReqs = []
        for spCtxt, spServer, spSettings in setupPkts:
            if spCtxt[0] == 0:
                print "Using a context with high ID = 0 for packet requests might not do what you want!!!"
            p = self.client[spServer].packet(context=spCtxt)
            for spSetting, spData in spSettings:
                p[spSetting](spData)
            setupReqs.append(p)

        bg = self.boardGroups[devs[0].serverName, devs[0].port]
        return bg.run(devices, reps, setupReqs, getTimingData, timingOrder, c['master_sync'], set(setupState))
        

    @setting(42, 'Daisy Chain', boards='*s', returns='*s')
    def daisy_chain(self, c, boards=None):
        """Set or get daisy chain board order.

        Set this to an empty list to run the selected board only.
        """
        if boards is None:
            boards = c['daisy_chain']
        else:
            c['daisy_chain'] = boards
        return boards

    @setting(43, 'Start Delay', delays='*w', returns='*w')
    def start_delay(self, c, delays=None):
        """Set start delays in ns for SRAM in the daisy chain.

        Must be the same length as daisy_chain for sequence to execute.
        """
        if delays is None:
            delays = c['start_delay']
        else:
            c['start_delay'] = delays
        return delays

    @setting(44, 'Timing Order', boards='*s', returns=['*s', ''])
    def timing_order(self, c, boards=None):
        """Set or get the timing order for boards.
        
        This specifies the boards from which you want to receive timing
        data, and the order in which the timing data should be returned.
        """
        if boards is None:
            boards = c['timing_order']
        else:
            c['timing_order'] = boards
        return boards

    @setting(45, 'Master Sync', sync='w', returns='w')
    def master_sync(self, c, sync=None):
        """Set or get the master sync.
        
        This specifies a counter that determines when the master
        is allowed to start, to control the microwave phase.  The
        default is 249, which sets the master to start only every 1 us.
        """
        if sync is None:
            sync = c['master_sync']
        else:
            c['master_sync'] = sync
        return sync

    @setting(49, 'Performance Data', returns='*((sw)(*v, v, v, v))')
    def performance_data(self, c):
        """Get data about the pipeline performance.
        
        For each board group (defined by direct ethernet server and port),
        this returns times for:
            page locks
            run lock
            run packet (on the direct ethernet server)
            read lock
        If the packet runs dry, the first time that will go to zero should
        be the run packet wait time. 
        """
        ans = []
        for server, port in sorted(self.boardGroups.keys()):
            group = self.boardGroups[server, port]
            pageTimes = [T.Value(lock.meanTime(), 's') for lock in group.pageLocks]
            runTime = T.Value(group.runLock.meanTime(), 's')
            readTime = T.Value(group.readLock.meanTime(), 's')
            if len(group.runWaitTimes):
                runWaitTime = sum(group.runWaitTimes) / len(group.runWaitTimes)
            else:
                runWaitTime = 0
            runWaitTime = T.Value(runWaitTime, 's')
            ans.append(((server, port), (pageTimes, runTime, runWaitTime, readTime)))
        return ans


    # TODO: make sure that low-level commands are compatible with board group operations.

    @setting(50, 'Debug Output', data='(wwww)', returns='')
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


    @setting(51, 'Run SRAM', data='*w', loop='b', returns='(ww)')
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

        data = numpy.array(data, dtype='uint32').tostring()
        #data = struct.pack('I'*len(data), *data)
        r = yield dev.sendSRAM(data)

        encode = lambda a: [a & 0xFF, (a>>8) & 0xFF, (a>>16) & 0xFF]
        pkt = [hdr, 0] + [0]*11 + encode(r[0]) + encode(r[1]-1) + [0]*37
        yield dev.sendRegisters(pkt, readback=False)
        returnValue(r)


    @setting(100, 'I2C', data='*w', returns='*w')
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


    @setting(110, 'LEDs', data=['w', '(bbbbbbbb)'], returns='w')
    def leds(self, c, data):
        """Sets the status of the 8 I2C LEDs."""
        dev = self.selectedDevice(c)

        if isinstance(data, tuple):
            # convert to a list of digits, and interpret as binary int
            data = long(''.join(str(int(b)) for b in data), 2)

        yield dev.runI2C([200, 68, data & 255])  # 192 for build 1
        returnValue(data)


    @setting(120, 'Reset Phasor', returns='b: phase detector output')
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
                  returns='b: phase detector output')
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

    @setting(130, 'Vout', chan='s', V='v[V]', returns='w')
    def vout(self, c, chan, V):
        """Sets the output voltage of any Vout channel, A, B, C or D."""
        cmd = getCommand({'A': 16, 'B': 18, 'C': 20, 'D': 22}, chan)
        dev = self.selectedDevice(c)
        val = int(max(min(round(V*0x3333), 0x10000), 0))
        pkt = [154, cmd, (val >> 8) & 0xFF, val & 0xFF]
        yield dev.runI2C(pkt)
        returnValue(val)
        

    @setting(135, 'Ain', returns='v[V]')
    def ain(self, c):
        """Reads the voltage on Ain."""
        dev = self.selectedDevice(c)
        pkt = [144, 0, 258, 145, 257, 256]
        r = yield dev.runI2C(pkt)
        returnValue(T.Value(((r[0]<<8) + r[1])/819.0, 'V'))


    @setting(200, 'PLL', data=['w', '*w'], returns='*w')
    def pll(self, c, data):
        """Sends a command or a sequence of commands to the PLL

        The returned WordList contains any read-back values.
        It has the same length as the sent list.
        """
        dev = self.selectedDevice(c)
        return dev.runSerial(1, data)

    @setting(204, 'DAC', chan='s', data=['w', '*w'], returns='*w')
    def dac_cmd(self, c, chan, data):
        """Send a command or sequence of commands to either DAC.

        The DAC channel must be either 'A' or 'B'.
        The returned list of words contains any read-back values.
        It has the same length as the sent list.
        """
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDevice(c)
        return dev.runSerial(cmd, data)


    @setting(206, 'DAC Clock Polarity', chan='s', invert='b', returns='b')
    def dac_pol(self, c, chan, invert):
        """Sets the clock polarity for either DAC.

        This command does not immediately update the clock polarity.
        Another command that sends a packet is needed.
        """
        cmds = getCommand({'A': (0x10, 0x11), 'B': (0x20, 0x22)}, chan)
        dev = self.selectedDevice(c)
        pkt = numpy.zeros(56, dtype='uint8')
        pkt[:2] = 0, 1
        pkt[46] = cmds[invert]
        yield dev.sendRegisters(pkt)
        returnValue(invert)


    @setting(210, 'PLL Init', returns='')
    def init_pll(self, c, data):
        """Sends the initialization sequence to the PLL.

        The sequence is [0x1FC093, 0x1FC092, 0x100004, 0x000C11]."""
        dev = self.selectedDevice(c)
        yield dev.runSerial(1, [0x1fc093, 0x1fc092, 0x100004, 0x000c11])
        pkt = numpy.zeros(56, dtype='uint8')
        pkt[0] = 4
        yield dev.sendRegisters(pkt, readback=False)


    @setting(211, 'PLL Reset', returns='')
    def pll_reset(self, c):
        """Resets the FPGA internal GHz serializer PLLs
        """
        dev = self.selectedDevice(c)
        pkt = [0,1] + [0]*54
        pkt[46] = 0x80

        yield dev.sendRegisters(pkt)

    @setting(212, 'PLL Query', returns='b')
    def pll_query(self, c):
        """Checks the FPGA internal GHz serializer PLLs for lock failures.
        Returns T if any of the PLLs have lost lock since the last reset.
        """
        dev = self.selectedDevice(c)
        pkt = [0,1] + [0]*54
        r = yield dev.sendRegisters(pkt)

        returnValue((ord(r[58]) & 0x80)>0)


    @setting(220, 'DAC Init', chan='s', signed='b', returns='b')
    def init_dac(self, c, chan, signed=False):
        """Sends an initialization sequence to either DAC.
        
        For unsigned data, this sequence is 0026, 0006, 1603, 0500
        For signed data, this sequence is 0024, 0004, 1603, 0500
        """
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDevice(c)
        pkt = [0x0024, 0x0004, 0x1603, 0x0500] if signed else \
              [0x0026, 0x0006, 0x1603, 0x0500]
        yield dev.runSerial(cmd, pkt)
        returnValue(signed)


    @setting(221, 'DAC LVDS', chan='s', data='w', returns='(www*(bb))')
    def dac_lvds(self, c, chan, data=None):
        """Set or determine DAC LVDS phase shift and return y, z check data."""
        cmd = getCommand({'A': 2, 'B': 3}, chan)
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


    @setting(222, 'DAC FIFO', chan='s', returns='(wwbww)')
    def dac_fifo(self, c, chan):
        """Moves the LVDS into a region where the FIFO counter is stable,
        adjusts the clock polarity and phase offset to make FIFO counter = 3,
        and finally returns LVDS setting back to original value
        """
        op = getCommand({'A': 2, 'B': 3}, chan)
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


    @setting(223, 'DAC Cross Controller', chan='s', delay='i', returns='i')
    def dac_xctrl(self, c, chan, delay=0):
        """Sets the cross controller delay on either DAC

        Range for delay is -63 to 63.
        """
        dev = self.selectedDevice(c)
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        if delay < -63 or delay > 63:
            raise T.Error(11, 'Delay must be between -63 and 63')

        seq = [0x0A00, 0x0B00 - delay] if delay < 0 else \
              [0x0A00 + delay, 0x0B00]
        yield dev.runSerial(cmd, seq)
        returnValue(delay)


    @setting(225, 'DAC BIST', chan='s', data='*w', returns='(b(ww)(ww)(ww))')
    def dac_bist(self, c, chan, data):
        """Run a BIST on the given SRAM sequence."""
        cmd, shift = getCommand({'A': (2, 0), 'B': (3, 14)}, chan)
        dev = self.selectedDevice(c)
        pkt = [4, 0] + [0]*54
        yield dev.sendRegisters(pkt, readback=False)

        dat = [d & 0x3FFF for d in data]
        data = [0, 0, 0, 0] + [d << shift for d in dat]
        # make sure data is at least 20 words long by appending 0's
        data += [0] * (20-len(data))
        data = numpy.array(data, dtype='uint32').tostring()
        #data = struct.pack('I'*len(data), *data)
        r = yield dev.sendSRAM(data)
        yield dev.runSerial(cmd, [0x0004, 0x1107, 0x1106])

        encode = lambda a: [a & 0xFF, (a>>8) & 0xFF, (a>>16) & 0xFF]
        pkt = [4, 0] + [0]*11 + encode(r[0]) + encode(r[1]-1) + [0]*37
        yield dev.sendRegisters(pkt, readback=False)

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

def getCommand(cmds, chan):
    """Get a command from a dictionary of commands.

    Raises a helpful error message if the given channel is not allowed.
    """
    try:
        return cmds[chan]
    except:
        raise Exception("Allowed channels are %s." % sorted(cmds.keys()))

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
    """Ensure that a piece of data is a list."""
    return data if isinstance(data, list) else [data]

def words2str(list):
    """Convert a list of ints to a byte string."""
    return py_array('B', list).tostring()

# commands for analyzing and manipulating FPGA memory sequences

def sequenceTime(cmds):
    """Conservative estimate of the length of a sequence in seconds."""
    cycles = sum(cmdTime(c) for c in cmds)
    return cycles * 40e-9 # assume 25 MHz clock -> 40 ns per cycle
    
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

def shiftSRAM(cmds, page):
    """Shift the addresses of SRAM calls for different pages.

    Takes a list of memory commands and a page number and
    modifies the commands for calling SRAM to point to the
    appropriate page.
    """
    for i, cmd in enumerate(cmds):
        opcode, address = (cmd >> 20) & 0xF, cmd & 0xFFFFF
        if opcode in [0x8, 0xA]: 
            address += page * SRAM_PAGE_LEN
            cmds[i] = (opcode << 20) + address

def maxSRAM(cmds):
    """Determines the maximum SRAM address used in a memory sequence.

    This is used to determine whether a given memory sequence is pageable,
    since only half of the available SRAM can be used when paging.
    """
    def addr(cmd):
        opcode, address = (cmd >> 20) & 0xF, cmd & 0xFFFFF
        return address if opcode in [0x8, 0xA] else 0
    return max(addr(cmd) for cmd in cmds)

def rangeSRAM(cmds):
    """Determines the min and max SRAM address used in a memory sequence.

    This is used to determine what portion of the SRAM sequence needs to be
    uploaded before running the board.
    """
    def addr(cmd):
        opcode, address = (cmd >> 20) & 0xF, cmd & 0xFFFFF
        return address if opcode in [0x8, 0xA] else 0
    addrs = [addr(cmd) for cmd in cmds]
    return min(addrs), max(addrs)


def timerCount(cmds):
    """Return the number of timer stops in a memory sequence.

    This should correspond to the number of timing results per
    repetition of the sequence.  Note that this method does no
    checking of the timer logic, for example whether every stop
    has a corresponding start.  That sort of checking is the
    user's responsibility at this point (if using the qubit server,
    these things are automatically checked).
    """
    #return numpy.sum(numpy.asarray(cmds) == 0x400001) # numpy version
    return cmds.count(0x400001) # python list version
    
    

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
