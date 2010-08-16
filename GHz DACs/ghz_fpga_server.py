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
name = GHz FPGA Server
version = 3.0.0
description = Talks to DAC and ADC boards

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from __future__ import with_statement

import itertools
import struct
import time

import numpy as np

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T
from labrad.devices import DeviceServer
from labrad.server import setting

import adc
import dac
from util import TimedLock


NUM_PAGES = 2

SRAM_LEN = 10240 #10240 words = 8192
SRAM_PAGE_LEN = 5120 #4096
SRAM_DELAY_LEN = 1024
SRAM_BLOCK0_LEN = 8192
SRAM_BLOCK1_LEN = 2048
SRAM_WRITE_PKT_LEN = 256 # number of words in each SRAM write packet
SRAM_WRITE_PAGES = SRAM_LEN / SRAM_WRITE_PKT_LEN # number of pages for writing SRAM

MASTER_SRAM_DELAY = 2 # microseconds for master to delay before SRAM to ensure synchronization

TIMING_PACKET_LEN = 30

TIMEOUT_FACTOR = 10 # timing estimates are multiplied by this factor to determine sequence timeout

I2C_RB = 0x100
I2C_ACK = 0x200
I2C_RB_ACK = I2C_RB | I2C_ACK
I2C_END = 0x400

# TODO: make sure paged operations (datataking) don't conflict with e.g. bringup
# - want to do this by having two modes for boards, either 'test' mode
#   (when a board does not belong to a board group) or 'production' mode
#   (when a board does belong to a board group).  It would be nice if boards
#   could be dynamically moved between groups, but we'll see about that...
# TODO: store memory and SRAM as numpy arrays, rather than lists and strings, respectively
# TODO: run sequences to verify the daisy-chain order automatically
# TODO: when running adc boards in demodulation (streaming mode), check counters to verify that there is no packet loss




class TimeoutError(Exception):
    """Error raised when boards timeout."""


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
    def __init__(self, fpgaServer, server, port):
        self.fpgaServer = fpgaServer
        self.server = server
        self.port = port
        self.cxn = server._cxn
        self.ctx = server.context()
        self.pageNums = itertools.cycle(range(NUM_PAGES))
        self.pageLocks = [TimedLock() for _ in range(NUM_PAGES)]
        self.runLock = TimedLock()
        self.readLock = TimedLock()
        self.setupState = set()
        self.runWaitTimes = []
        self.prevTriggers = 0
    
    @inlineCallbacks
    def init(self):
        """Set up the direct ethernet server in our own context."""
        p = self.server.packet(context=self.ctx)
        p.connect(self.port)
        yield p.send()
    
    @inlineCallbacks
    def shutdown(self):
        """When this board group is removed, expire our direct ethernet context."""
        yield self.cxn.manager.expire_context(self.server.ID, context=self.ctx)
        
    def configure(self, name, boards):
        """Update configuration for this board group."""
        self.name = name
        self.boardOrder = ['%s %s' % (name, boardName) for (boardName, delay) in boards]
        self.boardDelays = [delay for (boardName, delay) in boards]
        
    @inlineCallbacks
    def detectBoards(self):
        """Detect boards on the ethernet adapter managed by this board group.
        
        The autodetect operation is guarded by board group locks so that it
        will not conflict with sequences running on this board group.
        """
        try:
            # acquire all locks so we can ping boards without
            # interfering with board group operations
            for pageLock in self.pageLocks:
                yield pageLock.acquire()
            yield self.runLock.acquire()
            yield self.readLock.acquire()
            
            # detect each board type in its own context
            detections = [self.detectDACs(), self.detectADCs()]
            answer = yield defer.DeferredList(detections, consumeErrors=True)
            found = []
            for success, results in answer:
                if success:
                    found.extend(results)
                else:
                    print 'autodetect error:'
                    results.printTraceback()
            
            returnValue(found)
        finally:
            # release all locks once we're done with autodetection
            for pageLock in self.pageLocks:
                pageLock.release()
            self.runLock.release()
            self.readLock.release()

    def detectDACs(self, timeout=1.0):
        """Try to detect DAC boards on this board group."""
        def callback(src, data):
            board = int(src[-2:], 16)
            info = dac.processReadback(data)
            build = info['build']
            devName = '%s DAC %d' % (self.name, board)
            args = devName, self.server, self.port, board, build
            return (devName, args)
        macs = [dac.macFor(board) for board in range(256)]
        return self.doDetection(macs, dac.regPing(), dac.READBACK_LEN, callback)
    
    def detectADCs(self, timeout=1.0):
        """Try to detect ADC boards on this board group."""
        def callback(src, data):
            board = int(src[-2:], 16)
            info = adc.processReadback(data)
            build = info['build']
            devName = '%s ADC %d' % (self.name, board)
            args = devName, self.server, self.port, board, build
            return (devName, args)
        macs = [adc.macFor(board) for board in range(256)]
        return self.doDetection(macs, adc.regAdcPing(), adc.READBACK_LEN, callback)

    @inlineCallbacks
    def doDetection(self, macs, packet, respLength, callback, timeout=1.0):
        """Try to detect a boards at the specified mac addresses.
        
        For each response of the correct length received within the timeout from
        one of the given mac addresses, the callback function will be called and
        should return data to be added to the list of found devices. 
        """
        try:
            ctx = self.server.context()
            
            # prepare and send detection packets
            p = self.server.packet()
            p.connect(self.port)
            p.require_length(respLength)
            p.timeout(T.Value(timeout, 's'))
            p.listen()
            for mac in macs:
                p.destination_mac(mac)
                p.write(packet.tostring())
            yield p.send(context=ctx)
            
            # listen for responses
            start = time.time()
            found = []
            while (len(found) < len(macs)) and (time.time() - start < timeout):
                try:
                    ans = yield self.server.read(context=ctx)
                    src, dst, eth, data = ans
                    if src in macs:
                        devInfo = callback(src, data)
                        found.append(devInfo)
                except T.Error:
                    break
        finally:
            # expire the detection context
            yield self.cxn.manager.expire_context(self.server.ID, context=ctx)
        returnValue(found)


    def makePackets(self, devs, page, reps, timingOrder, sync=249):
        """Make packets to run a sequence on this board group.

        Running a sequence has 4 stages:
        - Load memory and SRAM into all boards in parallel.
          If possible, this is done in the background using a separate
          page while another sequence is running.

        - Run sequence by firing a single packet that starts all boards.
          To ensure synchronization the slaves are started first, in
          daisy-chain order, followed at the end by the master.

        - Collect timing data to ensure that the sequence is finished.
          We instruct the direct ethernet server to collect the packets
          but not send them yet.  Once collected, direct ethernet triggers
          are used to immediately start the next sequence if one was
          loaded into the next page.

        - Read timing data.
          Having started the next sequence (if one was waiting) we now
          read the timing data collected by the direct ethernet server,
          process it and return it.

        This function prepares the LabRAD packets that will be sent for
        each of these steps, but does not actually send anything.  By
        preparing these packets in advance we save time later when we
        are in the time-critical pipeline sections
        """
        # dictionary of devices to be run
        deviceInfo = dict((dev[0].devName, dev) for dev in devs)
        
        # load memory and SRAM
        loadPkts = []
        for board in self.boardOrder:
            if board in deviceInfo:
                dev, mem, sram = deviceInfo[board]
                if not len(loadPkts):
                    # this will be the master, so add delays before SRAM
                    mem = addMasterDelay(mem)
                if isinstance(sram, tuple):
                    sram, delay = sram
                loadPkts.append(dev.load(mem, sram, page))
        
        # run all boards (master last)
        boards = []
        for board, delay in zip(self.boardOrder, self.boardDelays):
            if board in deviceInfo:
                # this board will run
                dev, mem, sram = deviceInfo[board]
                # check for boards running multi-block sequences
                if isinstance(sram, tuple):
                    sram, blockDelay = sram
                else:
                    blockDelay = None
                slave = len(boards) > 0 # the first board is master
                regs = dac.regRun(page, slave, delay, blockDelay=blockDelay, sync=sync)
                boards.append((dev, regs))
            elif len(master):
                # this board is after the master, but will
                # not itself run, so we put it in idle mode
                # TODO: how do we put ADC boards in idle mode?
                dev = self.fpgaServer.devices[board] # look up the device wrapper
                regs = dac.regIdle(delay)
                boards.append((dev, regs))
        boards = boards[1:] + boards[0] # move master to the end
        runPkts = self.makeRunPackets(boards)
        
        # collect and read (or discard) timing results
        collectPkts = []
        readPkts = []
        for dev, mem, sram in devs:
            nTimers = timerCount(mem)
            N = reps * nTimers / TIMING_PACKET_LEN
            seqTime = TIMEOUT_FACTOR * (sequenceTime(mem) * reps) + 1
             
            collectPkts.append(dev.collect(N, seqTime, self.ctx))
            
            wantResults = timingOrder is None or dev.devName in timingOrder
            readPkts.append(dev.read(N) if wantResults else dev.discard(N))

        return loadPkts, runPkts, collectPkts, readPkts

    def makeRunPackets(self, data):
        """Create packets to run a set of boards.
        
        There are two options as to how this can work, depending on
        whether the setup state from the previous run is the same as
        for this run.  If no changes to the setup state are required,
        then we can wait for triggers and immediately start the next
        run; this is what the 'both' packet does.  If the setup state
        has changed, we must wait for triggers, then send setup packets,
        and then start the next run.  This two-stage operation is what
        the 'wait' and 'run' packets do.  We create both here because
        we can't tell until it is our turn in the pipe which method
        will be used.
        """
        wait = self.server.packet(context=self.ctx)
        run = self.server.packet(context=self.ctx)
        both = self.server.packet(context=self.ctx)
        # wait for triggers and discard them
        wait.wait_for_trigger(0, key='nTriggers')
        both.wait_for_trigger(0, key='nTriggers')
        # run all boards
        for dev, regs in data:
            bytes = regs.tostring()
            run.destination_mac(dev.MAC).write(bytes)
            both.destination_mac(dev.MAC).write(bytes)
        return wait, run, both

    @inlineCallbacks
    def run(self, devs, reps, setupPkts, setupState, sync, getTimingData, timingOrder):
        """Run a sequence on this board group."""
        if not all((d[0].serverName == self.server._labrad_name) and
                   (d[0].port == self.port) for d in devs):
            raise Exception('All boards must belong to the same board group!')
        boardOrder = [d[0].devName for d in devs]

        # check whether this is a multiblock sequence
        if any(isinstance(sram, tuple) for dev, mem, sram in devs):
            print 'Multi-block SRAM sequence'
            # update sram calls in memory sequences to the correct addresses
            # also pad sram blocks to take up full space and disable paging
            def fixSRAM(dev):
                dev, mem, sram = dev
                mem = fixSRAMaddresses(mem, sram)
                if isinstance(sram, tuple):
                    block0, block1, delay = sram
                    data = '\x00' * (SRAM_BLOCK0_LEN*4 - len(block0)) + block0 + block1
                    sram = (data, delay)
                return dev, mem, sram
            devs = [fixSRAM(dev) for dev in devs]
            
        # check whether this sequence will fit in just one page
        if all(maxSRAM(mem) <= SRAM_PAGE_LEN for dev, mem, sram in devs):
            # shorten SRAM to at most one page
            devs = [(dev, mem, sram if sram is None else sram[:SRAM_PAGE_LEN*4])
                    for dev, mem, sram in devs]
            # lock just one page
            page = self.pageNums.next()
            pageLocks = [self.pageLocks[page]]
        else:
            # start on page 0 and lock all pages
            print 'Paging off: SRAM too long.'
            page = 0
            pageLocks = self.pageLocks
        
        # prepare packets
        pkts = self.makePackets(devs, page, reps, timingOrder, sync)
        loadPkts, runPkts, collectPkts, readPkts = pkts
        
        try:
            # stage 1: load
            for pageLock in pageLocks: # lock pages to be written
                yield pageLock.acquire()
            loadDone = self.sendAll(loadPkts, 'Load', boardOrder)
            
            # stage 2: run
            runNow = self.runLock.acquire() # get in line to be the next to run
            try:
                yield loadDone # wait until load is finished
                yield runNow # now acquire the run lock
                
                # set the number of triggers, based on the last executed sequence
                waitPkt, runPkt, bothPkt = runPkts
                waitPkt['nTriggers'] = self.prevTriggers
                bothPkt['nTriggers'] = self.prevTriggers
                self.prevTriggers = len(devs) # store the number of triggers for the next run
                
                needSetup = (not setupState) or (not self.setupState) or (not (setupState <= self.setupState))
                if needSetup:
                    # we require changes to the setup state
                    r = yield waitPkt.send() # if this fails, something BAD happened!
                    try:
                        yield self.sendAll(setupPkts, 'Setup')
                        self.setupState = setupState
                    except Exception:
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
                    
                yield self.readLock.acquire() # wait for our turn to read data
                
                # collect appropriate number of packets and then trigger the run context
                collectAll = defer.DeferredList([p.send() for p in collectPkts], consumeErrors=True)
            finally:
                # by releasing the runLock, we allow the next sequence to send its run packet.
                # if our collect fails due to a timeout, however, our triggers will not all
                # be sent to the run context, so that it will stay blocked until after we cleanup
                # cleanup and send the necessary triggers
                self.runLock.release()
            
            # wait for data to be collected (or timeout)
            results = yield collectAll
        finally:
            for pageLock in reversed(pageLocks):
                pageLock.release()
        
        # check for a timeout and recover if necessary
        if not all(success for success, result in results):
            yield self.recoverFromTimeout(devs, results)
            self.readLock.release()
            raise TimeoutError(self.timeoutReport(devs, results))
        
        # no timeout, so go ahead and read data
        readAll = self.sendAll(readPkts, 'Read', boardOrder)
        self.readLock.release()
        results = yield readAll # wait for read to complete

        if getTimingData:
            if timingOrder is not None:
                if timingMode == 'DAC' or timingMode == 'AVERAGE':
                    results = [results[boardOrder.index(board)] for board in timingOrder]
                elif timingMode == 'DEMOD':
                    results = [results[boardOrder.index(board)] for board, channel in timingOrder]
            results = [[data for src, dst, eth, data in r['read']] for r in results]
            if len(results):
                timing = np.vstack(self.extractTiming(result) for result in results)
            else:
                timing = []
            returnValue(timing)

    @inlineCallbacks
    def sendAll(self, packets, info, infoList=None):
        """Send a list of packets and wrap them up in a deferred list."""
        results = yield defer.DeferredList([p.send() for p in packets], consumeErrors=True)
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
                    m = 'OK' if s else ('error!\n' + r.getBriefTraceback())
                    msg += str(i) + (': %s\n\n' % m)
            raise Exception(msg)
        
    def extractTiming(self, packets):
        """Extract timing data coming back from a readPacket."""
        data = ''.join(data[3:63] for data in packets)
        return np.fromstring(data, dtype='<u2')

    @inlineCallbacks
    def recoverFromTimeout(self, devs, results):
        """Recover from a timeout error so that pipelining can proceed.
        
        We clear the packet buffer for all boards, whether or not
        they succeeded.  For boards that failed, we also send a
        trigger to unlock the run context.
        """
        for dev, (success, result) in zip(devs, results):
            ctx = None if success else self.ctx
            yield dev[0].clear(triggerCtx=ctx).send()
        
    def timeoutReport(self, devs, results):
        """Create a nice error message explaining which boards timed out."""
        lines = ['Some boards failed:']
        for dev, (success, result) in collectResults:
            line = dev[0].devName + ': ' + ('OK' if success else 'timeout!')
            lines.append(line)
        return '\n'.join(lines)



class FPGAServer(DeviceServer):
    """Server for GHz DAC and ADC boards.
    """
    name = 'GHz FPGAs'
    retries = 5
    
    @inlineCallbacks
    def initServer(self):
        self.boardGroups = {}
        yield DeviceServer.initServer(self)
    
    @inlineCallbacks
    def loadBoardGroupConfig(self):
        print 'Loading board group definitions from registry...'
        p = self.client.registry.packet()
        p.cd(['', 'Servers', 'GHz FPGAs'], True)
        p.get('boardGroups', True, [], key='boardGroups')
        ans = yield p.send()
        print 'Board group definitions loaded.'
        # validate board group definitions
        print 'Validating board group definitions.'
        valid = True
        names = set()
        adapters = set()
        for name, server, port, boards in ans['boardGroups']:
            if name in names:
                print "Multiple board groups with name '%s'" % name
                valid = False
            names.add(name)
            if (server, port) in adapters:
                print "Multiple board groups for adapter (%s, %s)" % (server, port)
                valid = False
            adapters.add((server, port))
        if valid:
            self.boardGroupDefs = ans['boardGroups']
            print 'Board group definitions ok.'
        else:
            print 'Please fix the board group configuration.'
    

    @inlineCallbacks    
    def adapterExists(self, server, port):
        """Check whether the specified ethernet adapter exists."""
        cxn = self.client
        if server not in cxn.servers:
            returnValue(False)
        else:
            de = cxn.servers[server]
            adapters = yield de.adapters()
            if len(adapters):
                ports, names = zip(*adapters)
            else:
                ports, names = [], []
            returnValue(port in ports)
    
        
    @inlineCallbacks
    def findDevices(self):
        print 'Refreshing client connection...'
        cxn = self.client
        yield cxn.refresh()
        
        # reload the board group configuration from the registry
        yield self.loadBoardGroupConfig()
        config = dict(((server, port), (name, boards))
                      for name, server, port, boards in self.boardGroupDefs)
        
        # determine what board groups are to be added, removed and kept as is
        existing = set(self.boardGroups.keys())
        configured = set((server, port) for name, server, port, boards in self.boardGroupDefs)
        
        additions = configured - existing
        removals = existing - configured
        keepers = existing - removals
        
        # check each addition to see whether the desired server/port exists
        for key in set(additions):
            server, port = key
            exists = yield self.adapterExists(server, port)
            if not exists:
                print "Adapter '%s' (port %d) does not exist.  Group will not be added." % (server, port)
                additions.remove(key)
        
        # check each keeper to see whether the server/port still exists
        for key in set(keepers):
            server, port = key
            exists = yield self.adapterExists(server, port)
            if not exists:
                print "Adapter '%s' (port %d) does not exist.  Group will be removed." % (server, port)
                keepers.remove(key)
                removals.add(key)                
        
        print 'Board groups to be added:', additions
        print 'Board groups to be removed:', removals
        
        # remove board groups which are no longer configured
        for key in removals:
            bg = self.boardGroups[key]
            del self.boardGroups[key]
            yield bg.shutdown()
        
        # add new board groups
        for server, port in additions:
            name, boards = config[server, port]
            print "Creating board group '%s': server='%s', port=%d" % (name, server, port)
            de = cxn.servers[server]
            boardGroup = BoardGroup(self, de, port)
            yield boardGroup.init()
            self.boardGroups[server, port] = boardGroup
            
        
        # update configuration of all board groups and detect devices
        detections = []
        groupNames = []
        for (server, port), boardGroup in self.boardGroups.items():
            name, boards = config[server, port]
            boardGroup.configure(name, boards)
            detections.append(boardGroup.detectBoards())
            groupNames.append(name)
        answer = yield defer.DeferredList(detections, consumeErrors=True)
        found = []
        for name, (success, result) in zip(groupNames, answer):
            if success:
                if len(result):
                    print "Devices detected on board group '%s':" % name
                    for devName, args in result:
                        print " ", devName
                else:
                    print "No devices detected on board group '%s'." % name
                found.extend(result)
            else:
                print "Autodetection failed on board group '%s':" % name
                result.printBriefTraceback(elideFrameworkCode=1)
        returnValue(found)


    def deviceWrapper(self, guid, name):
        """Build a DAC or ADC device wrapper, depending on the device name"""
        if 'ADC' in name:
            return adc.AdcDevice(guid, name)
        else:
            return dac.DacDevice(guid, name)


    ## Trigger refreshes if a direct ethernet server connects or disconnects
    def serverConnected(self, ID, name):
        if "Direct Ethernet" in name:
            self.refreshDeviceList()

    def serverDisconnected(self, ID, name):
        if "Direct Ethernet" in name:
            self.refreshDeviceList()


    ## allow selecting different kinds of devices in each context
    def selectedDAC(self, context):
        dev = self.selectedDevice(context)
        if not isinstance(dev, DacDevice):
            raise Exception("selected device is not a DAC board")
        
    def selectedADC(self, context):
        dev = self.selectedDevice(context)
        if not isinstance(dev, AdcDevice):
            raise Exception("selected device is not an ADC board")

    def getBoardGroup(self, name):
        """Find a board group by name."""
        for boardGroup in self.boardGroups.values():
            if boardGroup.name == name:
                return boardGroup
        raise Exception("Board group '%s' not found." % name)


    def initContext(self, c):
        """Initialize a new context."""
        c['daisy_chain'] = []
        c['timing_order'] = None
        c['master_sync'] = 249

    ## remote settings

    @setting(1, 'List Devices', boardGroup='s', returns='*(ws)')
    def list_devices(self, c, boardGroup=None):
        """List available devices.
        
        If the optional boardGroup argument is specified, then only those
        devices belonging to that board group will be included.
        """
        IDs, names = self.deviceLists()
        devices = zip(IDs, names)
        if boardGroup is not None:
            bg = self.getBoardGroup(boardGroup) # make sure this board group exists
            devices = [(id, name) for (id, name) in devices if name.startswith(boardGroup)]
        return devices

    @setting(10, 'List Board Groups', returns='*s')
    def list_board_groups(self, c):
        """Get a list of existing board groups."""
        return sorted(bg.name for bg in self.boardGroups.values())


    ## Memory and SRAM upload


    @setting(20, 'SRAM', data='*w: SRAM Words to be written', returns='')
    def dac_sram(self, c, data):
        """Writes data to the SRAM at the current starting address.
        
        Data can be specified as a list of 32-bit words, or a pre-flattened byte string.
        """
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        if not isinstance(data, str):
            data = data.asarray.tostring()
        d['sram'] = data


    @setting(21, 'SRAM dual block',
             block1='*w: SRAM Words for first block',
             block2='*w: SRAM Words for second block',
             delay='w: nanoseconds to delay',
             returns='')
    def dac_sram_dual_block(self, c, block1, block2, delay):
        """Writes a dual-block SRAM sequence with a delay between the two blocks."""
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        sram = d.get('sram', '')
        if not isinstance(block1, str):
            block1 = block1.asarray.tostring()
        if not isinstance(block2, str):
            block2 = block2.asarray.tostring()
        delayPad = delay % SRAM_DELAY_LEN
        delayBlocks = delay / SRAM_DELAY_LEN
        # add padding to beginning of block2 to get delay right
        block2 = block1[-4:] * delayPad + block2
        # add padding to end of block2 to ensure that we have a multiple of 4
        endPad = 4 - (len(block2) / 4) % 4
        if endPad != 4:
            block2 = block2 + block2[-4:] * endPad
        d['sram'] = (block1, block2, delayBlocks)


    @setting(30, 'Memory', data='*w: Memory Words to be written',
                           returns='')
    def dac_memory(self, c, data):
        """Writes data to the Memory at the current starting address."""
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        d['mem'] = data


    @setting(40, 'ADC Filter Func', bytes='s', stretchLen='w', stretchAt='w', returns='')
    def adc_filter_func(self, c, bytes, stretchLen=0, stretchAt=0):
        """Set the filter function to be used with the selected ADC board. (ADC only)
        
        Each byte specifies the filter weight for a 4ns interval.  In addition,
        you can specify a stretch which will repeat a value in the middle of the filter
        for the specified length (in 4ns intervals).
        """
        assert len(bytes) <= adc.FILTER_LEN, 'Filter function max length is %d' % adc.FILTER_LEN
        dev = self.selectedADC(c)
        bytes = np.fromstring(bytes, dtype='<u1')
        d = c.setdefault(dev, {})
        d['filterFunc'] = bytes
        d['filterStretchLen'] = stretchLen
        d['filterStretchAt'] = stretchAt
    
    
    @setting(41, 'ADC Trig Magnitude', channel='w', sineAmp='w', cosineAmp='w', returns='')
    def adc_trig_magnitude(self, c, channel, sineAmp, cosineAmp):
        """Set the magnitude of sine and cosine functions for a demodulation channel. (ADC only)
        
        The channel indicates which demodulation channel to use, in the range 0 to N-1 where
        N is the number of channels (currently 4).  sineAmp and cosineAmp are the magnitudes
        of the respective sine and cosine functions, ranging from 0 to 255.
        """
        assert 0 <= channel < adc.DEMOD_CHANNELS, 'channel out of range: %d' % channel
        assert 0 <= sineAmp <= adc.TRIG_AMP, 'sine amplitude out of range: %d' % sineAmp
        assert 0 <= cosineAmp <= adc.TRIG_AMP, 'cosine amplitude out of range: %d' % cosineAmp
        dev = self.selectedADC(c)
        d = c.setdefault(dev, {})
        ch = d.setdefault(channel, {})
        ch['sineAmp'] = sineAmp
        ch['cosineAmp'] = cosineAmp
        phi = np.pi/2 * (np.arange(256) + 0.5) / 256
        ch['sine'] = np.floor(sineAmp * np.sin(phi) + 0.5).astype('uint8')
        ch['cosine'] = np.floor(cosineAmp * np.cos(phi) + 0.5).astype('uint8')
    
    
    @setting(42, 'ADC Demod Phase', channel='w', dphi='i', phi0='i', returns='')
    def adc_demod_frequency(self, c, channel, dphi, phi0=0):
        """Set the phase difference and initial phase for a demodulation channel. (ADC only)
        
        The phase difference gives the phase change per 2ns.
        """
        assert -2**15 <= dphi < 2**15, 'delta phi out of range'
        assert -2**15 <= phi0 < 2**15, 'phi0 out of range'
        dev = self.selectedADC(c)
        d = c.setdefault(dev, {})
        ch = d.setdefault(channel, {})
        ch['dphi'] = dphi
        ch['phi0'] = phi0


    @setting(50, 'Run Sequence', reps='w', getTimingData='b',
                                 setupPkts='?{(((ww), s, ((s?)(s?)(s?)...))...)}',
                                 setupState='*s',
                                 returns=['*2w', ''])
    def sequence_run(self, c, reps=30, getTimingData=True, setupPkts=[], setupState=[]):
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
        # TODO: also handle ADC boards here
        
        # Round stats up to multiple of the timing packet length
        reps += TIMING_PACKET_LEN - 1
        reps -= reps % TIMING_PACKET_LEN
        
        if len(c['daisy_chain']):
            # run multiple boards, with first board as master
            devs = [self.getDevice(c, name) for name in c['daisy_chain']]
        else:
            # run the selected device only
            devs = [self.selectedDAC(c)]
        mems = [c.get(dev, {}).get('mem', None) for dev in devs]
        srams = [c.get(dev, {}).get('sram', None) for dev in devs]
        devices = zip(devs, mems, srams)
        if getTimingData:
            if c['timing_order'] is None:
                timingOrder = [d.devName for d in devs]
            else:
                timingOrder = c['timing_order']
        else:
            timingOrder = []

        # build setup requests
        setupReqs = []
        for spCtxt, spServer, spSettings in setupPkts:
            if spCtxt[0] == 0:
                print 'Using a context with high ID = 0 for packet requests might not do what you want!!!'
            p = self.client[spServer].packet(context=spCtxt)
            for spRec in spSettings:
                if len(spRec) == 2:
                    spSetting, spData = spRec
                    p[spSetting](spData)
                elif len(spRec) == 1:
                    spSetting, = spRec
                    p[spSetting]()
                else:
                    raise Exception('Malformed setup packet: ctx=%s, server=%s, settings=%s' % (spCtxt, spServer, spSettings))
            setupReqs.append(p)

        bg = self.boardGroups[devs[0].serverName, devs[0].port]
        retries = self.retries
        attempt = 1
        while True:
            try:
                ans = yield bg.run(devices, reps, setupReqs, set(setupState), c['master_sync'], getTimingData, timingOrder)
                returnValue(ans)
            except TimeoutError, err:
                # log attempt to stdout and file
                import os
                userpath = os.path.expanduser('~')
                logpath = os.path.join(userpath, 'dac_timeout_log.txt')
                with open(logpath, 'a') as logfile:
                    print 'attempt %d - error: %s' % (attempt, err)
                    print >>logfile, 'attempt %d - error: %s' % (attempt, err)
                    if attempt == retries:
                        print 'FAIL!'
                        print >>logfile, 'FAIL!'
                        raise
                    else:
                        print 'retrying...'
                        print >>logfile, 'retrying...'
                        attempt += 1
    
    
    @setting(52, 'Daisy Chain', boards='*s', returns='*s')
    def sequence_boards(self, c, boards=None):
        """Set or get the boards to run.

        The actual daisy chain order is determined automatically, as configured
        in the registry for each board group.  This setting controls which set of
        boards to run, but does not determine the order.  Set daisy_chain to an
        empty list to run the currently-selected board only.
        """
        if boards is None:
            boards = c['daisy_chain']
        else:
            c['daisy_chain'] = boards
        return boards

    @setting(54, 'Timing Order', boards='*s', returns='*s')
    def sequence_timing_order(self, c, boards=None):
        """Set or get the timing order for boards.
        
        This specifies the boards from which you want to receive timing
        data, and the order in which the timing data should be returned.
        """
        if boards is None:
            boards = c['timing_order']
        else:
            c['timing_order'] = boards
        return boards

    @setting(55, 'Master Sync', sync='w', returns='w')
    def sequence_master_sync(self, c, sync=None):
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

    @setting(59, 'Performance Data', returns='*((sw)(*v, *v, *v, *v, *v))')
    def sequence_performance_data(self, c):
        """Get data about the pipeline performance.
        
        For each board group (as defined in the registry),
        this returns times for:
            page lock (page 0)
            page lock (page 1)
            run lock
            run packet (on the direct ethernet server)
            read lock

        If the pipe runs dry, the first time that will go to zero will
        be the run packet wait time.  In other words, if you have non-zero
        times for the run-packet wait, then the pipe is saturated,
        and the experiment is running at full capacity.
        """
        ans = []
        for server, port in sorted(self.boardGroups.keys()):
            group = self.boardGroups[server, port]
            pageTimes = [lock.times for lock in group.pageLocks]
            runTime = group.runLock.times
            runWaitTime = group.runWaitTimes
            readTime = group.readLock.times
            ans.append(((server, port), (pageTimes[0], pageTimes[1], runTime, runWaitTime, readTime)))
        return ans


    @setting(200, 'PLL Init', returns='')
    def pll_init(self, c, data):
        """Sends the initialization sequence to the PLL. (DAC and ADC)

        The sequence is [0x1FC093, 0x1FC092, 0x100004, 0x000C11].
        """
        dev = self.selectedDevice(c)
        yield dev.initPLL()


    @setting(201, 'PLL Reset', returns='')
    def pll_reset(self, c):
        """Resets the FPGA internal GHz serializer PLLs. (DAC only)"""
        dev = self.selectedDAC(c)
        regs = regPllReset()
        yield dev.sendRegisters(regs)


    @setting(202, 'PLL Query', returns='b')
    def pll_query(self, c):
        """Checks the FPGA internal GHz serializer PLLs for lock failures. (DAC and ADC)

        Returns True if the PLL has lost lock since the last reset.
        """
        dev = self.selectedDevice(c)
        unlocked = yield dev.queryPLL()
        returnValue(unlocked)



    @setting(1080, 'DAC Debug Output', data='(wwww)', returns='')
    def dac_debug_output(self, c, data):
        """Outputs data directly to the output bus. (DAC only)"""
        dev = self.selectedDAC(c)
        pkt = regDebug(*data)
        yield dev.sendRegisters(pkt)


    @setting(1081, 'DAC Run SRAM', data='*w', loop='b', blockDelay='w', returns='')
    def dac_run_sram(self, c, data, loop=False, blockDelay=0):
        """Loads data into the SRAM and executes. (DAC only)

        If loop is True, the sequence will be repeated forever,
        otherwise it will be executed just once.  Sending
        an empty list of data will clear the SRAM.  The blockDelay
        parameters specifies the number of microseconds to delay
        for a multiblock sequence.
        """
        dev = self.selectedDAC(c)

        pkt = regPing()
        yield dev.sendRegisters(pkt)

        if not len(data):
            returnValue((0, 0))

        if loop:
            # make sure data is at least 20 words long by repeating it
            data *= (20-1)/len(data) + 1
        else:
            # make sure data is at least 20 words long by repeating first value
            data += [data[0]] * (20-len(data))
            
        data = np.array(data, dtype='<u4').tostring()
        yield dev.sendSRAM(data)
        startAddr, endAddr = 0, len(data) / 4

        pkt = regRunSram(startAddr, endAddr, loop, blockDelay)
        yield dev.sendRegisters(pkt, readback=False)


    @setting(1100, 'DAC I2C', data='*w', returns='*w')
    def dac_i2c(self, c, data):
        """Runs an I2C Sequence (DAC only)

        The entries in the WordList to be sent have the following meaning:
          0..255 : send this byte
          256:     read back one byte without acknowledging it
          512:     read back one byte with ACK
          1024:    send data and start new packet
        For each 256 or 512 entry in the WordList to be sent, the read-back byte is appended to the returned WordList.
        In other words: the length of the returned list is equal to the count of 256's and 512's in the sent list.
        """
        dev = self.selectedDAC(c)
        
        # split a list into sublists delimited by a sentinel value
        def partition(l, sentinel):
            if len(l) == 0:
                return []
            try:
                i = l.index(sentinel) # find next occurence of sentinel
                rest = partition(l[i+1:], sentinel) # partition rest of list
                if i > 0:
                    return [l[:i]] + rest
                else:
                    return rest
            except ValueError: # no more sentinels
                return [l]
            
        # split data into packets delimited by I2C_END
        pkts = partition(data, I2C_END)
        
        return dev.runI2C(pkts)


    @setting(1110, 'DAC LEDs', data=['w', 'bbbbbbbb'], returns='w')
    def dac_leds(self, c, data):
        """Sets the status of the 8 I2C LEDs. (DAC only)"""
        dev = self.selectedDAC(c)

        if isinstance(data, tuple):
            # convert to a list of digits, and interpret as binary int
            data = long(''.join(str(int(b)) for b in data), 2)

        pkts = [[200, 68, data & 0xFF]] # 192 for build 1
        yield dev.runI2C(pkts)  
        returnValue(data)


    @setting(1120, 'DAC Reset Phasor', returns='b: phase detector output')
    def dac_reset_phasor(self, c):
        """Resets the clock phasor. (DAC only)"""
        dev = self.selectedDAC(c)

        pkts = [[152, 0, 127, 0],  # set I to 0 deg
                [152, 34, 254, 0], # set Q to 0 deg
                [112, 65],         # set enable bit high
                [112, 193],        # set reset high
                [112, 65],         # set reset low
                [112, 1],          # set enable low
                [113, I2C_RB]]     # read phase detector

        r = yield dev.runI2C(pkts)
        returnValue((r[0] & 1) > 0)


    @setting(1121, 'DAC Set Phasor',
                  data=[': poll phase detector only',
                        'v[rad]: set angle (in rad, deg, \xF8, \', or ")'],
                  returns='b: phase detector output')
    def dac_set_phasor(self, c, data=None):
        """Sets the clock phasor angle and reads the phase detector bit. (DAC only)"""
        dev = self.selectedDAC(c)

        if data is None:
            pkts = [[112, 1],
                    [113, I2C_RB]]
        else:
            sn = int(round(127 + 127*np.sin(data))) & 0xFF
            cs = int(round(127 + 127*np.cos(data))) & 0xFF
            pkts = [[152,  0, sn, 0],
                    [152, 34, cs, 0],
                    [112, 1],
                    [113, I2C_RB]]
                   
        r = yield dev.runI2C(pkts)
        returnValue((r[0] & 1) > 0)

    @setting(1130, 'DAC Vout', chan='s', V='v[V]', returns='w')
    def dac_vout(self, c, chan, V):
        """Sets the output voltage of any Vout channel, A, B, C or D. (DAC only)"""
        cmd = getCommand({'A': 16, 'B': 18, 'C': 20, 'D': 22}, chan)
        dev = self.selectedDAC(c)
        val = int(max(min(round(V*0x3333), 0x10000), 0))
        pkts = [[154, cmd, (val >> 8) & 0xFF, val & 0xFF]]
        yield dev.runI2C(pkts)
        returnValue(val)
        

    @setting(1135, 'DAC Ain', returns='v[V]')
    def dac_ain(self, c):
        """Reads the voltage on Ain. (DAC only)"""
        dev = self.selectedDAC(c)
        pkts = [[144, 0],
                [145, I2C_RB_ACK, I2C_RB]]
        r = yield dev.runI2C(pkts)
        returnValue(T.Value(((r[0] << 8) + r[1]) / 819.0, 'V'))


    @setting(1200, 'DAC PLL', data=['w', '*w'], returns='*w')
    def dac_pll(self, c, data):
        """Sends a command or a sequence of commands to the PLL. (DAC only)

        The returned WordList contains any read-back values.
        It has the same length as the sent list.
        """
        dev = self.selectedDAC(c)
        return dev.runSerial(1, data)

    @setting(1204, 'DAC Serial Command', chan='s', data=['w', '*w'], returns='*w')
    def dac_cmd(self, c, chan, data):
        """Send a command or sequence of commands to either DAC. (DAC only)

        The DAC channel must be either 'A' or 'B'.
        The returned list of words contains any read-back values.
        It has the same length as the sent list.
        """
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)
        return dev.runSerial(cmd, data)


    @setting(1206, 'DAC Clock Polarity', chan='s', invert='b', returns='b')
    def dac_pol(self, c, chan, invert):
        """Sets the clock polarity for either DAC. (DAC only)"""
        regs = regClockPolarity(chan, invert)
        dev = self.selectedDAC(c)
        yield dev.sendRegisters(regs)
        returnValue(invert)


    @setting(1220, 'DAC Init', chan='s', signed='b', returns='b')
    def dac_init(self, c, chan, signed=False):
        """Sends an initialization sequence to either DAC. (DAC only)
        
        For unsigned data, this sequence is 0026, 0006, 1603, 0500
        For signed data, this sequence is 0024, 0004, 1603, 0500
        """
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)
        pkt = [0x0024, 0x0004, 0x1603, 0x0500] if signed else \
              [0x0026, 0x0006, 0x1603, 0x0500]
        yield dev.runSerial(cmd, pkt)
        returnValue(signed)


    @setting(1221, 'DAC LVDS', chan='s', data='w', returns='(www*(bb))')
    def dac_lvds(self, c, chan, data=None):
        """Set or determine DAC LVDS phase shift and return y, z check data. (DAC only)"""
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)
        pkt = [[0x0400 + (i<<4), 0x8500, 0x0400 + i, 0x8500][j]
               for i in range(16) for j in range(4)]

        if data is None:
            answer = yield dev.runSerial(cmd, [0x0500] + pkt)
            answer = [answer[i*2+2] & 1 for i in range(32)]

            MSD = -2
            MHD = -2
            for i in range(16):
                if MSD == -2 and answer[i*2] == 1: MSD = -1
                if MSD == -1 and answer[i*2] == 0: MSD = i
                if MHD == -2 and answer[i*2+1] == 1: MHD = -1
                if MHD == -1 and answer[i*2+1] == 0: MHD = i
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


    @setting(1222, 'DAC FIFO', chan='s', returns='(wwbww)')
    def dac_fifo(self, c, chan):
        """Adjust FIFO buffer. (DAC only)
        
        Moves the LVDS into a region where the FIFO counter is stable,
        adjusts the clock polarity and phase offset to make FIFO counter = 3,
        and finally returns LVDS setting back to original value.
        """
        op = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)

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
            if pkt[0] >= 0x0600:
                raise Exception('Failed to find clock edge while setting FIFO counter!')
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
            except Exception:
                clkinv = not clkinv
                yield self.dac_pol(c, chan, clkinv)

        if not found:
            raise Exception('Cannot find a FIFO offset to get a counter value of 3! Found: ' + repr(reading))

        # return to old lvds setting
        pkt = range(newlvds, oldlvds, -32)[1:] + [oldlvds]
        yield dev.runSerial(op, pkt)
        ans = (oldlvds >> 4) & 15, (newlvds >> 4) & 15, clkinv, PHOF, reading
        returnValue(ans)


    @setting(1223, 'DAC Cross Controller', chan='s', delay='i', returns='i')
    def dac_xctrl(self, c, chan, delay=0):
        """Sets the cross controller delay on either DAC. (DAC only)

        Range for delay is -63 to 63.
        """
        dev = self.selectedDAC(c)
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        if delay < -63 or delay > 63:
            raise T.Error(11, 'Delay must be between -63 and 63')

        seq = [0x0A00, 0x0B00 - delay] if delay < 0 else [0x0A00 + delay, 0x0B00]
        yield dev.runSerial(cmd, seq)
        returnValue(delay)


    @setting(1225, 'DAC BIST', chan='s', data='*w', returns='(b(ww)(ww)(ww))')
    def dac_bist(self, c, chan, data):
        """Run a BIST on the given SRAM sequence. (DAC only)"""
        cmd, shift = getCommand({'A': (2, 0), 'B': (3, 14)}, chan)
        dev = self.selectedDAC(c)
        pkt = regRunSram(0, 0, loop=False)
        yield dev.sendRegisters(pkt, readback=False)

        dat = [d & 0x3FFF for d in data]
        data = [0, 0, 0, 0] + [d << shift for d in dat]
        # make sure data is at least 20 words long by appending 0's
        data += [0] * (20-len(data))
        data = np.array(data, dtype='<u4').tostring()
        yield dev.sendSRAM(data)
        startAddr, endAddr = 0, len(data) / 4
        yield dev.runSerial(cmd, [0x0004, 0x1107, 0x1106])

        pkt = regRunSram(startAddr, endAddr, loop=False)
        yield dev.sendRegisters(pkt, readback=False)

        seq = [0x1126, 0x9200, 0x9300, 0x9400, 0x9500,
               0x1166, 0x9200, 0x9300, 0x9400, 0x9500,
               0x11A6, 0x9200, 0x9300, 0x9400, 0x9500,
               0x11E6, 0x9200, 0x9300, 0x9400, 0x9500]
        theory = tuple(bistChecksum(dat))
        bist = yield dev.runSerial(cmd, seq)
        reading = [(bist[i+4] <<  0) + (bist[i+3] <<  8) +
                   (bist[i+2] << 16) + (bist[i+1] << 24)
                   for i in [0, 5, 10, 15]]
        lvds, fifo = tuple(reading[0:2]), tuple(reading[2:4])

        # lvds and fifo may be reversed.  This is okay
        if tuple(reversed(lvds)) == theory:
            lvds = tuple(reversed(lvds))
        if tuple(reversed(fifo)) == theory:
            fifo = tuple(reversed(fifo))
        returnValue((lvds == theory and fifo == theory, theory, lvds, fifo))



    @setting(2500, 'ADC Recalibrate', returns='')
    def adc_recalibrate(self, c):
        """Recalibrate the analog-to-digital converters. (ADC only)"""
        dev = self.selectedADC(c)
        yield dev.recalibrate()
    
    
    @setting(2600, 'ADC Run Average', returns='*(i{I} i{Q})')
    def adc_run_average(self, c, channel, sineAmp, cosineAmp):
        """Run the selected ADC board once in average mode. (ADC only)
        
        The board will start immediately using the trig lookup and demod
        settings already specified in this context.  Returns the acquired
        I and Q waveforms.
        """
        dev = self.selectedADC(c)
        info = c.setdefault(dev, {})
        filterFunc = info.get('filterFunc', np.array([255], dtype='<u1'))
        filterStretchLen = info.get('filterStretchLen', 0)
        filterStretchAt = info.get('filterStretchAt', 0)
        demods = dict((i, info[i]) for i in range(adc.DEMOD_CHANNELS) if i in info)
        ans = yield dev.runAverage(filterFunc, filterStretchLen, filterStretchAt, demods)
        returnValue(ans)
    
    
    @setting(2601, 'ADC Run Demod', returns='*(i{I} i{Q}), (i{Imax} i{Imin} i{Qmax} i{Qmin})')
    def adc_run_demod(self, c, channel, sineAmp, cosineAmp):
        dev = self.selectedADC(c)
        info = c.setdefault(dev, {})
        filterFunc = info.get('filterFunc', np.array([255], dtype='<u1'))
        filterStretchLen = info.get('filterStretchLen', 0)
        filterStretchAt = info.get('filterStretchAt', 0)
        demods = dict((i, info[i]) for i in range(adc.DEMOD_CHANNELS) if i in info)
        ans = yield dev.runDemod(filterFunc, filterStretchLen, filterStretchAt, demods)
        returnValue(ans)
    
    # TODO: new settings
    # - set up ADC options for data readout, to be used with the next daisy-chain run
    #   - DAC boards: one number (timing result) per repetition
    #   - ADC boards: either one waveform (averaged) for whole run
    #                 or one demodulation packet for each repetition


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
    for i in xrange(0, len(data), 2):
        for j in xrange(2):
            if data[i+j] & 0x3FFF != 0:
                bist[j] = (((bist[j] << 1) & 0xFFFFFFFE) | ((bist[j] >> 31) & 1)) ^ ((data[i+j] ^ 0x3FFF) & 0x3FFF)
    return bist


# commands for analyzing and manipulating FPGA memory sequences

def sequenceTime(cmds):
    """Conservative estimate of the length of a sequence in seconds."""
    cycles = sum(cmdTime(c) for c in cmds)
    return cycles * 40e-9 # assume 25 MHz clock -> 40 ns per cycle

def getOpcode(cmd):
    return (cmd & 0xF00000) >> 20

def getAddress(cmd):
    return (cmd & 0x0FFFFF)

def cmdTime(cmd):
    """A conservative estimate of the number of cycles a given command takes."""
    opcode = getOpcode(cmd)
    abcde  = getAddress(cmd)
    xy     = (cmd & 0x00FF00) >> 8
    ab     = (cmd & 0x0000FF)

    if opcode in [0x0, 0x1, 0x2, 0x4, 0x8, 0xA]:
        return 1
    if opcode == 0xF:
        return 2
    if opcode == 0x3:
        return abcde + 1 # delay
    if opcode == 0xC:
        # TODO: incorporate SRAMoffset when calculating sequence time.  This gives a max of up to 12 + 255 us
        return 25*12 # maximum SRAM length is 12us, with 25 cycles per us

def addMasterDelay(cmds, delay=MASTER_SRAM_DELAY):
    """Add delays to master board before SRAM calls.
    
    Creates a memory sequence with delays added before all SRAM
    calls to ensure that boards stay properly synchronized by
    allowing extra time for slave boards to reach the SRAM
    synchronization point.  The delay is specified in microseconds.
    """
    newCmds = []
    cycles = int(delay * 25) & 0x0FFFFF
    delayCmd = 0x300000 + cycles
    for cmd in cmds:
        if getOpcode(cmd) == 0xC: # call SRAM?
            newCmds.append(delayCmd) # add delay
        newCmds.append(cmd)
    return newCmds

def shiftSRAM(cmds, page):
    """Shift the addresses of SRAM calls for different pages.

    Takes a list of memory commands and a page number and
    modifies the commands for calling SRAM to point to the
    appropriate page.
    """
    def shiftAddr(cmd):
        opcode, address = getOpcode(cmd), getAddress(cmd)
        if opcode in [0x8, 0xA]: 
            address += page * SRAM_PAGE_LEN
            return (opcode << 20) + address
        else:
            return cmd
    return [shiftAddr(cmd) for cmd in cmds]

def fixSRAMaddresses(mem, sram):
    """Set the addresses of SRAM calls for multiblock sequences.

    Takes a list of memory commands and an sram sequence (which
    will be a tuple of blocks for a multiblock sequence) and updates
    the call SRAM commands to the correct addresses. 
    """
    if not isinstance(sram, tuple):
        return mem
    sramCalls = sum(getOpcode(cmd) == 0xC for cmd in mem)
    if sramCalls > 1:
        raise Exception('Only one SRAM call allowed in multi-block sequences.')
    def fixAddr(cmd):
        opcode, address = getOpcode(cmd), getAddress(cmd)
        if opcode == 0x8:
            # SRAM start address
            address = SRAM_BLOCK0_LEN - len(sram[0])/4
            return (opcode << 20) + address
        elif opcode == 0xA:
            # SRAM end address
            address = SRAM_BLOCK0_LEN + len(sram[1])/4 + SRAM_DELAY_LEN * sram[2]
            return (opcode << 20) + address
        else:
            return cmd
    return [fixAddr(cmd) for cmd in cmds]

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
    return sum(np.asarray(cmds) == 0x400001) # numpy version
    #return cmds.count(0x400001) # python list version
    

__server__ = FPGAServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
