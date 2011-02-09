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
name = GHz FPGAs
version = 3.1.1
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
import sys
import os
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

from matplotlib import pyplot as plt

NUM_PAGES = 2

MASTER_SRAM_DELAY = 2 # microseconds for master to delay before SRAM to ensure synchronization

TIMEOUT_FACTOR = 10 # timing estimates are multiplied by this factor to determine sequence timeout

I2C_RB = 0x100
I2C_ACK = 0x200
I2C_RB_ACK = I2C_RB | I2C_ACK
I2C_END = 0x400

# TODO: Remove the constants from above and put them in the registry to be read by individual DAC board instances. See DacDevice.connect to see how this is done
# TODO: make sure paged operations (datataking) don't conflict with e.g. bringup
# - want to do this by having two modes for boards, either 'test' mode
#   (when a board does not belong to a board group) or 'production' mode
#   (when a board does belong to a board group).  It would be nice if boards
#   could be dynamically moved between groups, but we'll see about that...
# TODO: store memory and SRAM as numpy arrays, rather than lists and strings, respectively
# TODO: run sequences to verify the daisy-chain order automatically
# TODO: when running adc boards in demodulation (streaming mode), check counters to verify that there is no packet loss
# TODO: think about whether page selection and pipe semaphore can interact badly to slow down pipelining


class TimeoutError(Exception):
    """Error raised when boards timeout."""
    
class BoardGroup(object):
    """Manages a group of GHz DAC boards that can be run simultaneously.
    
    All the fpga boards must be daisy-chained to allow for synchronization,
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
        #self.sourceMac = getLocalMac(port)
        self.pipeSemaphore = defer.DeferredSemaphore(NUM_PAGES)
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
        #p.source_mac(self.sourceMac)
        yield p.send()
    
    @inlineCallbacks
    def shutdown(self):
        """Clean up when this board group is removed."""
        # expire our context with the manager
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
            for i in xrange(NUM_PAGES):
                yield self.pipeSemaphore.acquire()
            for pageLock in self.pageLocks:
                yield pageLock.acquire()
            yield self.runLock.acquire()
            yield self.readLock.acquire()
            
            # detect each board type in its own context
            detections = [self.detectDACs(), self.detectADCs()]
            answer = yield defer.DeferredList(detections, consumeErrors=True)
            found = []
            for success, result in answer:
                if success:
                    found.extend(result)
                else:
                    print 'autodetect error:'
                    result.printTraceback()
            
            # clear any detection packets which may be buffered in device contexts
            #TODO: check that this actually clears packets
            devices = self.devices()
            clears = []
            for dev in devices:
                clears.append(dev.clear().send())
            
            returnValue(found)
        finally:
            # release all locks once we're done with autodetection
            for i in xrange(NUM_PAGES):
                self.pipeSemaphore.release()
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
            args = devName, self, self.server, self.port, board, build
            return (devName, args)
        macs = [dac.macFor(board) for board in range(256)]
        return self._doDetection(macs, dac.regPing(), dac.READBACK_LEN, callback)
    
    def detectADCs(self, timeout=1.0):
        """Try to detect ADC boards on this board group."""
        def callback(src, data):
            board = int(src[-2:], 16) #16 indicates number base for conversion from string to integer
            info = adc.processReadback(data)
            build = info['build']
            devName = '%s ADC %d' % (self.name, board)
            args = devName, self, self.server, self.port, board, build
            return (devName, args)
        macs = [adc.macFor(board) for board in range(256)]
        return self._doDetection(macs, adc.regAdcPing(), adc.READBACK_LEN, callback)

    @inlineCallbacks
    def _doDetection(self, macs, packet, respLength, callback, timeout=1.0):
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
            #p.source_mac(self.sourceMac)
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
                    src, dst, eth, data = yield self.server.read(context=ctx)
                    if src in macs:
                        devInfo = callback(src, data)
                        found.append(devInfo)
                except T.Error:
                    break # read timeout
            returnValue(found)
        finally:
            # expire the detection context
            yield self.cxn.manager.expire_context(self.server.ID, context=ctx)

    def devices(self):
        """Return a list of known device objects that belong to this board group."""
        return [dev for dev in self.fpgaServer.devices.values()
                    if dev.boardGroup == self]
        
    @inlineCallbacks
    def testMode(self, func, *a, **kw):
        """Call a function in test mode.
        
        This makes sure that all currently-executing pipeline stages
        are finished by acquiring the pipe semaphore for all pages,
        then runs the function, and finally releases the semaphore
        to allow the pipeline to continue.
        """
        for i in xrange(NUM_PAGES):
            yield self.pipeSemaphore.acquire()
        try:
            ans = yield func(*a, **kw)
            returnValue(ans)
        finally:
            for i in xrange(NUM_PAGES):
                self.pipeSemaphore.release()


    def makePackets(self, runners, page, reps, timingOrder, sync=249):
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
        runnerInfo = dict((runner.dev.devName, runner) for runner in runners)
        
        # upload sequence data (pipelined)
        loadPkts = []
        for board in self.boardOrder:
            if board in runnerInfo:
                runner = runnerInfo[board]
                isMaster = len(loadPkts) == 0
                p = runner.loadPacket(page, isMaster)
                if p is not None:
                    loadPkts.append(p)
        
        # setup board state (not pipelined)
        setupPkts = []
        for board in self.boardOrder:
            if board in runnerInfo:
                runner = runnerInfo[board]
                p = runner.setupPacket()
                if p is not None:
                    setupPkts.append(p)
        
        # run all boards (master last)
        boards = []
        for board, delay in zip(self.boardOrder, self.boardDelays):
            if board in runnerInfo:
                runner = runnerInfo[board]
                slave = len(boards) > 0
                regs = runner.runPacket(page, slave, delay, sync)
                boards.append((runner.dev, regs))
            elif len(boards):
                # this board is after the master, but will
                # not itself run, so we put it in idle mode
                dev = self.fpgaServer.devices[board] # look up the device wrapper
                if isinstance(dev, dac.DacDevice):
                    regs = dac.regIdle(delay)
                    boards.append((dev, regs))
                elif isinstance(dev, adc.AdcDevice):
                    # ADC boards always pass through signals, so no need for Idle mode
                    pass
        boards = boards[1:] + boards[:1] # move master to the end
        runPkts = self.makeRunPackets(boards)
        
        # collect and read (or discard) timing results
        seqTime = max(runner.seqTime for runner in runners)
        collectPkts = [runner.collectPacket(seqTime, self.ctx) for runner in runners]
        readPkts = [runner.readPacket(timingOrder) for runner in runners]
            
        return loadPkts, setupPkts, runPkts, collectPkts, readPkts

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
    def run(self, runners, reps, setupPkts, setupState, sync, getTimingData, timingOrder):
        """Run a sequence on this board group."""
        
        # check whether this sequence will fit in just one page
        if all(dev.pageable() for dev in runners):
            # lock just one page
            page = self.pageNums.next()
            pageLocks = [self.pageLocks[page]]
        else:
            # start on page 0 and set pageLocks to all pages.
            print 'Paging off: SRAM too long.'
            page = 0
            pageLocks = self.pageLocks
        
        # prepare packets
        pkts = self.makePackets(runners, page, reps, timingOrder, sync)
        loadPkts, boardSetupPkts, runPkts, collectPkts, readPkts = pkts
        
        # add setup packets from boards (ADCs) to that provided in the args
        setupPkts.extend(pkt for pkt, state in boardSetupPkts) # this is a list
        setupState.update(state for pkt, state in boardSetupPkts) # this is a set
        
        try:
            yield self.pipeSemaphore.acquire()
            try:
                # stage 1: load
                for pageLock in pageLocks: # lock pages to be written
                    yield pageLock.acquire()
                loadDone = self.sendAll(loadPkts, 'Load') #Send load packets. Do not wait for response.
                
                # stage 2: run
                runNow = self.runLock.acquire() # Send a request for the run lock, do not wait for response.
                try:
                    yield loadDone # wait until load is finished
                    yield runNow # Wait for acquisition of the run lock.
                    
                    # set the number of triggers, based on the last executed sequence
                    waitPkt, runPkt, bothPkt = runPkts
                    waitPkt['nTriggers'] = self.prevTriggers
                    bothPkt['nTriggers'] = self.prevTriggers
                    self.prevTriggers = len(runners) # store the number of triggers for the next run
                    
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
                    
                    # stage 3: collect
                    # collect appropriate number of packets and then trigger the run context
                    collectAll = defer.DeferredList([p.send() for p in collectPkts], consumeErrors=True)
                finally:
                    # by releasing the runLock, we allow the next sequence to send its run packet.
                    # if our collect fails due to a timeout, however, our triggers will not all
                    # be sent to the run context, so that it will stay blocked until after we
                    # cleanup and send the necessary triggers
                    self.runLock.release()
                
                # wait for data to be collected (or timeout)
                results = yield collectAll
            finally:
                for pageLock in pageLocks:
                    pageLock.release()
            
            # check for a timeout and recover if necessary
            if not all(success for success, result in results):
                for success, result in results:
                    if not success:
                        result.printTraceback()
                yield self.recoverFromTimeout(runners, results)
                self.readLock.release()
                raise TimeoutError(self.timeoutReport(runners, results))
            
            # stage 4: read
            # no timeout, so go ahead and read data
            boardOrder = [runner.dev.devName for runner in runners]
            readAll = self.sendAll(readPkts, 'Read', boardOrder)
            self.readLock.release()
            results = yield readAll # wait for read to complete
    
            if getTimingData:
                allDacs = True
                answers = []
                boardResults = {}
                for board in timingOrder:
                    channel = None
                    if '::' in board:
                        board, channel = board.split('::')
                        channel = int(channel)
                    
                    # extract data from ethernet packets if we have not already
                    if board in boardResults:
                        answer = boardResults[board]
                    else:
                        idx = boardOrder.index(board)
                        runner = runners[idx]
                        allDacs &= isinstance(runner, DacRunner)
                        result = [data for src, dest, eth, data in results[idx]['read']]
                        answer = runner.extract(result)
                        boardResults[board] = answer
                        
                    # add extracted data to the list of timing results
                    if channel is not None:
                        answer = answer[channel]
                    answers.append(answer)
                
                if allDacs and len(set(len(answer) for answer in answers)) == 1:
                    # make a 2D list for backward compatibility
                    answers = np.vstack(answers)
                else:
                    # otherwise make a tuple
                    answers = tuple(answers)
                returnValue(answers)
        finally:
            self.pipeSemaphore.release()

    @inlineCallbacks
    def sendAll(self, packets, info, infoList=None):
        """Send a list of packets and wrap them up in a deferred list."""
        results = yield defer.DeferredList([p.send() for p in packets], consumeErrors=True)#[(success, result)...]
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
        return np.fromstring(data, dtype='<u2').astype('u4')

    @inlineCallbacks
    def recoverFromTimeout(self, runners, results):
        """Recover from a timeout error so that pipelining can proceed.
        
        We clear the packet buffer for all boards, whether or not
        they succeeded.  For boards that failed, we also send a
        trigger to unlock the run context.
        """
        for runner, (success, result) in zip(runners, results):
            ctx = None if success else self.ctx
            yield runner.dev.clear(triggerCtx=ctx).send()
        
    def timeoutReport(self, runners, results):
        """Create a nice error message explaining which boards timed out."""
        lines = ['Some boards failed:']
        for runner, (success, result) in zip(runners, results):
            line = runner.dev.devName + ': ' + ('OK' if success else 'timeout!')
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
        yield self.loadBoardGroupConfig() #Creates self.boardGroupDefs
        config = dict(((server, port), (name, boards)) #The keys here are tuples!
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
            boardGroup = BoardGroup(self, de, port) #Sets attributes
            yield boardGroup.init()                 #Gets context with direct ethernet
            self.boardGroups[server, port] = boardGroup
        print self.boardGroups
        
        # update configuration of all board groups and detect devices
        detections = []
        groupNames = []
        for (server, port), boardGroup in self.boardGroups.items():
            name, boards = config[server, port]
            boardGroup.configure(name, boards)
            detections.append(boardGroup.detectBoards())        #Board detection#
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
        elif 'DAC' in name:
            return dac.DacDevice(guid, name)
        else:
            raise Exception('Device name does not correspond to a known device type')


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
        if not isinstance(dev, dac.DacDevice):
            raise Exception("selected device is not a DAC board")
        return dev
        
    def selectedADC(self, context):
        dev = self.selectedDevice(context)
        if not isinstance(dev, adc.AdcDevice):
            raise Exception("selected device is not an ADC board")
        return dev

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
        d = c.setdefault(dev, {}) #If c has a dev, return its value, otherwise insert do: c['dev']={} and return {}
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
        delayPad = delay % dev.params['SRAM_DELAY_LEN']
        delayBlocks = delay / dev.params['SRAM_DELAY_LEN']
        # add padding to beginning of block2 to get delay right
        block2 = block1[-4:] * delayPad + block2
        # add padding to end of block2 to ensure that we have a multiple of 4
        endPad = 4 - (len(block2) / 4) % 4
        if endPad != 4:
            block2 = block2 + block2[-4:] * endPad
        d['sram'] = (block1, block2, delayBlocks)

    @setting(22, 'SRAM Address', addr='w', returns='')
    def dac_sram_address(self, c, addr):
        """Sets address for next SRAM write.
        
        DEPRECATED: This function no longer does anything and you should not call it!
        """
        dev = self.selectedDAC(c)
        print 'Deprecation warning: SRAM Address called unnecessarily'

    @setting(30, 'Memory', data='*w: Memory Words to be written', returns='')
    def dac_memory(self, c, data):
        """Writes data to the Memory at the current starting address."""
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        d['mem'] = data


    # ADC configuration

    @setting(40, 'ADC Filter Func', bytes='s', stretchLen='w', stretchAt='w', returns='')
    def adc_filter_func(self, c, bytes, stretchLen=0, stretchAt=0):
        """Set the filter function to be used with the selected ADC board. (ADC only)
        
        Each byte specifies the filter weight for a 4ns interval.  In addition,
        you can specify a stretch which will repeat a value in the middle of the filter
        for the specified length (in 4ns intervals).
        """
        dev = self.selectedADC(c)
        assert len(bytes) <= dev.params['FILTER_LEN'], 'Filter function max length is %d' % dev.params['FILTER_LEN']
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
        
        dev = self.selectedADC(c) #Get the ADC selected in this context. Raise an exception if selected device is not an ADC
        assert 0 <= channel < dev.params['DEMOD_CHANNELS'], 'channel out of range: %d' % channel
        assert 0 <= sineAmp <= dev.params['TRIG_AMP'], 'sine amplitude out of range: %d' % sineAmp
        assert 0 <= cosineAmp <= dev.params['TRIG_AMP'], 'cosine amplitude out of range: %d' % cosineAmp
        d = c.setdefault(dev, {}) #d=c[dev] if c[dev] exists, otherwise makes c[dev]={} and returns c[dev]. Gives c its own representation of dev
        ch = d.setdefault(channel, {})
        ch['sineAmp'] = sineAmp
        ch['cosineAmp'] = cosineAmp
        N = dev.params['LOOKUP_TABLE_LEN']
        phi = np.pi/2 * (np.arange(N) + 0.5) / N
        ch['sine'] = np.floor(sineAmp * np.sin(phi) + 0.5).astype('uint8')      #Sine waveform for this channel
        ch['cosine'] = np.floor(cosineAmp * np.sin(phi) + 0.5).astype('uint8')  #Cosine waveform for this channel, note that the function is still a SINE function!

        
    @setting(42, 'ADC Demod Phase', channel='w', dPhi='i', phi0='i', returns='')
    def adc_demod_frequency(self, c, channel, dPhi, phi0=0):
        """Set the trig table address step and initial phase for a demodulation channel. (ADC only)
        
        dPhi: number of trig table addresses to step through each time sample (2ns for first version of board).
        
        The trig lookup table address is stored in a 16 bit accumulator. The lookup table has 1024
        addresses. The six least significant bits are ignored when accessing the accululator to read
        the lookup table. This gives sub-address timing resolution.
        
        The physical demodulation frequency is related to dPhi as follows:
        Since the least significant bits of the accumulator are dropped, it takes 2^6=64 clicks to
        increment the lookup table address by one. Therefore, if we incriment the accumulator by 1
        click each time step then we go through
        ((1/64)*Address)*(1 cycle/1024 Address) = (2**-16)cycle
        This happens every 2ns, so we have 2**-16 cycle/2ns = 2**-17 GHz = 7.629 KHz
        Therefore, dPhi = desiredFrequency/7629Hz.
        
        The initial phase works the same way. We specify a sixteen bit number to determine the initial lookup
        table address, but only the six least significant bits are dropped. Since the trig table is 2^10
        addresses long and once trip through the table is one cycle, you have to increment by 2^16 clicks to
        go through the table once. Therefore, the starting phase is determined as
        phi0 = phase0*(2^16)
        where phase0 is the starting phase in CYCLES!
        """
        assert -2**15 <= dPhi < 2**15, 'delta phi out of range' #16 bit 2's compliment number for demod trig function
        assert -2**15 <= phi0 < 2**15, 'phi0 out of range'
        dev = self.selectedADC(c)
        d = c.setdefault(dev, {})
        ch = d.setdefault(channel, {})
        ch['dPhi'] = dPhi
        ch['phi0'] = phi0
        

    @setting(44, 'ADC Run Mode', mode='s', returns='')
    def adc_run_mode(self, c, mode):
        """Set the run mode for the current ADC board, 'average' or 'demodulate'. (ADC only)
        """
        mode = mode.lower()
        assert mode in ['average', 'demodulate'], 'unknown mode: "%s"' % mode
        dev = self.selectedADC(c)
        d = c.setdefault(dev, {})   # if c[dev] exists, d = c[dev]. Otherwise d = {} and c[dev] = {} 
        d['runMode'] = mode         # d points to the same object as c[dev], which is MUTABLE. Mutating d mutates c[dev]!!!

    # @setting(45, 'ADC Start Delay', delay='w', returns='')
    # def adc_start_delay(self, c, delay):
        # """Specify the time to delay before starting ADC acquisition.  (ADC only)
        
        # The delay is specified in nanoseconds from the start of SRAM.  Note that
        # just as for DAC boards, the daisy-chain delays are compensated automatically,
        # so this delay should be relative to the start of the programmed SRAM sequence.
        # """
        # dev = self.selectedADC(c)
        # c.setdefault(dev, {})['startDelay'] = delay

    @setting(45, 'Start Delay', delay='w', returns='')
    def start_delay(self, c, delay):
        dev = self.selectedDevice(c)
        d = c.setdefault(dev, {})
        d['startDelay'] = delay

    @setting(46, 'ADC Demod Range', returns='i{Imax}, i{Imin}, i{Qmax}, i{Qmin}')
    def adc_demod_range(self, c):
        """Get the demodulation ranges for the last sequence run in this context. (ADC only)
        """
        dev = self.selectedADC(c)
        return c[dev]['ranges']



    # multiboard sequence execution

    @setting(50, 'Run Sequence', reps='w', getTimingData='b',
                                 setupPkts='?{(((ww), s, ((s?)(s?)(s?)...))...)}',
                                 setupState='*s',
                                 returns=['*2w', '?', ''])
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
            
        If only DAC boards are run and all boards return the same number of
        results (because all boards have the same number of timer calls),
        then a 2D list of results of type *2w will be returned.  Otherwise,
        a cluster of results will be returned, in the order specified by
        timing order.  Individual DAC boards always return *w; ADC boards in
        average mode return (*i,{I} *i{Q}); and ADC boards in demodulate
        mode also return (*i,{I} *i{Q}) for each channel.
        """
        # TODO: also handle ADC boards here
        
        # Round stats up to multiple of the timing packet length
        reps += dac.TIMING_PACKET_LEN - 1
        reps -= reps % dac.TIMING_PACKET_LEN
        
        if len(c['daisy_chain']):
            # run multiple boards, with first board as master
            devs = [self.getDevice(c, name) for name in c['daisy_chain']]
        else:
            # run the selected device only (must be a DAC)
            devs = [self.selectedDAC(c)]

        # check to make sure that all boards are in the same board group
        if len(set(dev.boardGroup for dev in devs)) > 1:
            raise Exception("Can only run multiboard sequence if all boards are in the same board group!")
        bg = devs[0].boardGroup
        
        # build a list of runners which have necessary sequence information for each board
        runners = []
        for dev in devs:
            if isinstance(dev, dac.DacDevice):
                info = c.get(dev, {}) #Default to empty dictionary if c['dev'] doesn't exist.
                mem = info.get('mem', None)
                startDelay = info.get('startDelay',0)
                sram = info.get('sram', None)
                runner = DacRunner(dev, reps, startDelay, mem, sram)
            elif isinstance(dev, adc.AdcDevice):
                info = c.get(dev, {})
                try:
                    runMode = info['runMode']
                except KeyError:
                    raise Exception("No runmode specified for ADC board '%s'" % dev.devName)
                try:
                    startDelay = info['startDelay']
                except KeyError:
                    raise Exception("No start delay specified for ADC board '%s'" % dev.devName)
                try:
                    filter = (info['filterFunc'], info['filterStretchLen'], info['filterStretchAt'])
                except KeyError:
                    raise Exception("No filter function specified for ADC board '%s'" % dev.devName)
                channels = dict((i, info[i]) for i in range(dev.params['DEMOD_CHANNELS']) if i in info)
                #for key,value in channels.items():
                #    print key,value
                runner = AdcRunner(dev, reps, runMode, startDelay, filter, channels)
            else:
                raise Exception("Unknown device type: %s" % dev) 
            runners.append(runner)       

        # determine timing order
        if getTimingData:
            if c['timing_order'] is None:
                if len(c['daisy_chain']):
                    # changed in this version: require timing order to be specified for multiple boards
                    raise Exception('You must specify a timing order to get data back from multiple boards')
                else:
                    # only running one board, which must be a DAC, so just get timing from it
                    timingOrder = [d.devName for d in devs]
            else:
                timingOrder = c['timing_order']
        else:
            timingOrder = []

        # build setup requests
        setupReqs = processSetupPackets(self.client, setupPkts)

        # run the sequence, with possible retries if it fails
        retries = self.retries
        attempt = 1
        while True:
            try:
                ans = yield bg.run(runners, reps, setupReqs, set(setupState), c['master_sync'], getTimingData, timingOrder)
                # for ADCs in demodulate mode, store their I and Q ranges to check for possible clipping
                for runner in runners:
                    if isinstance(runner, AdcRunner) and runner.runMode == 'demodulate':
                        c[runner.dev]['ranges'] = runner.ranges
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
        
        Boards not listed here will be set to idle mode, and will pass the daisychain
        pulse through to the next board.
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
        In addition, this will determine what kind of boards will return
        data (ADCs or DACs).  For ADC boards, the data specified here must
        agree with the selection made for run mode for that board.
        
        To get DAC timing data or ADC data in average mode, specify the
        device name as a string.  To get ADC data in demodulation mode,
        specify a string in the form "<device name>::<channel>" where
        channel is the demodulation channel number.
        
        Note that you can get data from more than one demodulation channel,
        so that a given ADC board can appear multiple times in the timing
        order, however each ADC board must be run either in average mode
        or demodulation mode, not both.
        
        Note that the boards parameter must be a list of strings, *s! If you
        send in a single string, pylabrad will accept it as a *s but it will
        be treated as a list of single character strings and you'll get unexpected
        behavior. For example, if you send in 'abcde' it will be treated like ['a','b','c','d','e'].
        
        Parameters:
        boards: INSERT EXAMPLE!!!
        """
        if boards is None:              #Get timing order
            boards = c['timing_order']
        else:                           #Set timing order
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
        for (server, port), group in sorted(self.boardGroups.items()):
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
        yield dev.resetPLL()


    @setting(202, 'PLL Query', returns='b')
    def pll_query(self, c):
        """Checks the FPGA internal GHz serializer PLLs for lock failures. (DAC and ADC)

        Returns True if the PLL has lost lock since the last reset.
        """
        dev = self.selectedDevice(c)
        unlocked = yield dev.queryPLL()
        returnValue(unlocked)

    @setting(203, 'Build Number', returns='s')
    def build_number(self, c):
        """Gets the build number of selected device (DAC and ADC)"""
        dev = self.selectedDevice(c)
        buildNumber = yield dev.buildNumber()
        returnValue(buildNumber)

    @setting(1080, 'DAC Debug Output', data='wwww', returns='')
    def dac_debug_output(self, c, data):
        """Outputs data directly to the output bus. (DAC only)"""
        dev = self.selectedDAC(c)
        yield dev.debugOutput(*data)


    @setting(1081, 'DAC Run SRAM', data='*w', loop='b', blockDelay='w', returns='')
    def dac_run_sram(self, c, data, loop=False, blockDelay=0):
        """Loads data into the SRAM and executes as master. (DAC only)

        If loop is True, the sequence will be repeated forever,
        otherwise it will be executed just once.  Sending
        an empty list of data will clear the SRAM.  The blockDelay
        parameters specifies the number of microseconds to delay
        for a multiblock sequence.
        """
        if not len(data):
            return

        if loop:
            # make sure data is at least 20 words long by repeating it
            data *= (20-1)/len(data) + 1
        else:
            # make sure data is at least 20 words long by repeating first value
            data += [data[0]] * (20-len(data))

        dev = self.selectedDAC(c)
        yield dev.runSram(data, loop, blockDelay)


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


    @setting(1200, 'DAC PLL', data='*w', returns='*w')
    def dac_pll(self, c, data):
        """Sends a sequence of commands to the PLL. (DAC only)

        The returned WordList contains any read-back values.
        It has the same length as the sent list.
        """
        dev = self.selectedDAC(c)
        return dev.runSerial(1, data)

    @setting(1204, 'DAC Serial Command', chan='s', data='*w', returns='*w')
    def dac_cmd(self, c, chan, data):
        """Send a sequence of commands to either DAC. (DAC only)

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
        dev = self.selectedDAC(c)
        yield dev.setPolarity(chan, invert)
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


    @setting(1221, 'DAC LVDS', chan='s', data='w', returns='www*(bb)')
    def dac_lvds(self, c, chan, data=None):
        """Set or determine DAC LVDS phase shift and return y, z check data. (DAC only)"""
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)
        ans = yield dev.setLVDS(cmd, data)
        returnValue(ans)


    @setting(1222, 'DAC FIFO', chan='s', returns='wwbww')
    def dac_fifo(self, c, chan):
        """Adjust FIFO buffer. (DAC only)
        
        Moves the LVDS into a region where the FIFO counter is stable,
        adjusts the clock polarity and phase offset to make FIFO counter = 3,
        and finally returns LVDS setting back to original value.
        """
        op = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)
        ans = yield dev.setFIFO(chan, op)
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


    @setting(1225, 'DAC BIST', chan='s', data='*w', returns='b(ww)(ww)(ww)')
    def dac_bist(self, c, chan, data):
        """Run a BIST on the given SRAM sequence. (DAC only)"""
        cmd, shift = getCommand({'A': (2, 0), 'B': (3, 14)}, chan)
        dev = self.selectedDAC(c)
        ans = yield dev.runBIST(cmd, shift, data)
        returnValue(ans)


    @setting(2500, 'ADC Recalibrate', returns='')
    def adc_recalibrate(self, c):
        """Recalibrate the analog-to-digital converters. (ADC only)"""
        dev = self.selectedADC(c)
        yield dev.recalibrate()
    
    
    @setting(2600, 'ADC Run Average', returns='*i{I}, *i{Q}')
    def adc_run_average(self, c):
        """Run the selected ADC board once in average mode. (ADC only)
        
        The board will start immediately using the trig lookup and demod
        settings already specified in this context (although these settings have
        no effect in average mode).  Returns the acquired I and Q waveforms.
        
        Returns:
        (I: np.array(int), Q: np.array(int))
        """
        dev = self.selectedADC(c)
        info = c.setdefault(dev, {})
        filterFunc = info.get('filterFunc', np.array([255], dtype='<u1'))   #Default to [255]
        filterStretchLen = info.get('filterStretchLen', 0)                  #Default to no stretch
        filterStretchAt = info.get('filterStretchAt', 0)                    #Default to stretch at 0
        demods = dict((i, info[i]) for i in range(dev.params['DEMOD_CHANNELS']) if i in info)
        ans = yield dev.runAverage(filterFunc, filterStretchLen, filterStretchAt, demods)
        returnValue(ans)

    @setting(2601, 'ADC Run Calibrate', returns='')
    def adc_run_calibrate(self, c):
        """Recalibrate the ADC chips
        """
        dev = self.selectedADC(c)
        info = c.setdefault(dev, {})
        filterFunc = info.get('filterFunc', np.array([255], dtype='<u1'))   #Default to [255]
        filterStretchLen = info.get('filterStretchLen', 0)                  #Default to no stretch
        filterStretchAt = info.get('filterStretchAt', 0)                    #Default to stretch at 0
        demods = dict((i, info[i]) for i in range(dev.params['DEMOD_CHANNELS']) if i in info)
        yield dev.runCalibrate()

        
    @setting(2602, 'ADC Run Demod', returns='((*i{I}, *i{Q}), (i{Imax} i{Imin} i{Qmax} i{Qmin}))')
    #@setting(2602, 'ADC Run Demod', returns='*i')
    def adc_run_demod(self, c):
        dev = self.selectedADC(c)
        info = c.setdefault(dev, {})
        filterFunc = info.get('filterFunc', np.array(dev.params['FILTER_LEN']*[128], dtype='<u1')) #Default to full length filter with half full scale amplitude
        filterStretchLen = info.get('filterStretchLen', 0)
        filterStretchAt = info.get('filterStretchAt', 0)
        demods = dict((i, info[i]) for i in range(dev.params['DEMOD_CHANNELS']) if i in info)
        ans = yield dev.runDemod(filterFunc, filterStretchLen, filterStretchAt, demods)
        
        returnValue(ans)
    
    # TODO: new settings
    # - set up ADC options for data readout, to be used with the next daisy-chain run
    #   - DAC boards: one number (timing result) per repetition
    #   - ADC boards: either one waveform (averaged) for whole run
    #                 or one demodulation packet for each repetition



# Runners contain information for running a sequence on a particular board
#
# other info these should provide:
# - what to upload
# - whether upload is optional (based on setup state)
# - how many packets to expect, based on repetitions
# - whether discard is possible

class DacRunner(object):
    def __init__(self, dev, reps, startDelay, mem, sram):
        self.dev = dev
        self.reps = reps
        self.startDelay = startDelay
        self.mem = mem
        self.sram = sram
        self.blockDelay = None
        self._fixDualBlockSram()
        
        if self.pageable():
            # shorten our sram data so that it fits in one page
            self.sram = self.sram[:self.dev.params['SRAM_PAGE_LEN']*4]
        
        # calculate memory sequence time
        self.memTime = sequenceTime(self.mem)
        self.nTimers = timerCount(self.mem)
        self.nPackets = self.reps * self.nTimers / dac.TIMING_PACKET_LEN
        self.seqTime = TIMEOUT_FACTOR * (self.memTime * self.reps) + 1
    
    def pageable(self):
        """Check whether sequence fits in one page, based on SRAM addresses called by mem commands"""
        return maxSRAM(self.mem) <= self.dev.params['SRAM_PAGE_LEN']
    
    def _fixDualBlockSram(self):
        """If this sequence is for dual-block sram, fix memory addresses and build sram.
        
        Note that because the sram sequence will be padded to take up the entire first block
        of SRAM (before the delay section), this will automatically disable paging.
        """
        if isinstance(self.sram, tuple):
            # update addresses in memory commands that call into SRAM
            self.mem = fixSRAMaddresses(self.mem, self.sram, self.dev)
            
            # combine blocks into one sram sequence to be uploaded
            block0, block1, delay = self.sram
            data = '\x00' * (self.dev.params['SRAM_BLOCK0_LEN']*4 - len(block0)) + block0 + block1
            self.sram = data
            self.blockDelay = delay
    
    def loadPacket(self, page, isMaster):
        """Create pipelined load packet.  For DAC, upload mem and SRAM."""
        if isMaster:
            # this will be the master, so add delays before SRAM
            self.mem = addMasterDelay(self.mem)
            self.memTime = sequenceTime(self.mem) # recalculate sequence time
        return self.dev.load(self.mem, self.sram, page)
    
    def setupPacket(self):
        """Create non-pipelined setup packet.  For DAC, does nothing."""
        return None
    
    def runPacket(self, page, slave, delay, sync):
        """Create run packet."""
        startDelay = self.startDelay + delay
        regs = dac.regRun(self.reps, page, slave, startDelay, blockDelay=self.blockDelay, sync=sync)
        return regs
    
    def collectPacket(self, seqTime, ctx):
        """Collect appropriate number of ethernet packets for this sequence, then trigger run context."""
        return self.dev.collect(self.nPackets, seqTime, ctx)
    
    def readPacket(self, timingOrder):
        """Read (or discard) appropriate number of ethernet packets, depending on whether timing results are wanted."""
        keep = any(s.startswith(self.dev.devName) for s in timingOrder)
        return self.dev.read(self.nPackets) if keep else self.dev.discard(self.nPackets)
    
    def extract(self, packets):
        """Extract timing data coming back from a readPacket."""
        data = ''.join(data[3:63] for data in packets)
        return np.fromstring(data, dtype='<u2').astype('u4')

class AdcRunner(object):
    def __init__(self, dev, reps, runMode, startDelay, filter, channels):
        self.dev = dev
        self.reps = reps
        self.runMode = runMode
        self.startDelay = startDelay
        self.filter = filter
        self.channels = channels
        
        if self.runMode == 'average':
            self.mode = adc.RUN_MODE_AVERAGE_DAISY
            self.nPackets = self.dev.params['AVERAGE_PACKETS']
        elif self.runMode == 'demodulate':
            self.mode = adc.RUN_MODE_DEMOD_DAISY
            self.nPackets = reps
        else:
            raise Exception("Unknown run mode '%s' for board '%s'" % (self.runMode, self.dev.devName))
        self.seqTime = 0 # cannot estimate sequence time for ADC boards; DAC boards do this
        
    def pageable(self):
        """ADC sequence alone will never disable paging"""
        return True
    
    def loadPacket(self, page, isMaster):
        """Create pipelined load packet.  For ADC, nothing to do."""
        if isMaster:
            raise Exception("Cannot use ADC board '%s' as master." % self.dev.devName)
        return None

    def setupPacket(self):
        """Create non-pipelined setup packet.  For ADC, upload filter func and trig lookup tables."""
        return self.dev.setup(self.filter, self.channels)
    
    def runPacket(self, page, slave, delay, sync):
        """Create run packet.
        
        The unused arguments page, slave, and sync, in the call signature
        are there so that we could use the same call for DACs and ADCs.
        This is cheesey and ought to be fixed.
        """
        
        filterFunc, filterStretchLen, filterStretchAt = self.filter
        startDelay = self.startDelay + delay
        regs = adc.regAdcRun(self.mode, self.reps, filterFunc, filterStretchLen, filterStretchAt, self.channels, startDelay)
        return regs
    
    def collectPacket(self, seqTime, ctx):
        """Collect appropriate number of ethernet packets for this sequence, then trigger run context."""
        return self.dev.collect(self.nPackets, seqTime, ctx)
            
    def readPacket(self, timingOrder):
        """Read (or discard) appropriate number of ethernet packets, depending on whether timing results are wanted."""
        keep = any(s.startswith(self.dev.devName) for s in timingOrder)
        return self.dev.read(self.nPackets) if keep else self.dev.discard(self.nPackets)

    def extract(self, packets):
        """Extract timing data coming back from a readPacket."""
        if self.runMode == 'average':
            return adc.extractAverage(packets)
        elif self.runMode == 'demodulate':
            IQs, ranges = adc.extractDemod(packets)
            self.ranges = ranges # save this for possible access later
            return IQs


# some helper methods
    
def getCommand(cmds, chan):
    """Get a command from a dictionary of commands.

    Raises a helpful error message if the given channel is not allowed.
    """
    try:
        return cmds[chan]
    except:
        raise Exception("Allowed channels are %s." % sorted(cmds.keys()))

def processSetupPackets(cxn, setupPkts):
    """Process packets sent in flattened form into actual labrad packets on the given connection."""
    pkts = []
    for ctxt, server, settings in setupPkts:
        if ctxt[0] == 0:
            print 'Using a context with high ID = 0 for packet requests might not do what you want!!!'
        p = cxn[server].packet(context=ctxt)
        for rec in settings:
            if len(rec) == 2:
                setting, data = rec
                p[setting](data)
            elif len(rec) == 1:
                setting, = rec
                p[setting]()
            else:
                raise Exception('Malformed setup packet: ctx=%s, server=%s, settings=%s' % (ctxt, server, settings))
        pkts.append(p)
    return pkts


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
    if opcode in [0x0, 0x1, 0x2, 0x4, 0x8, 0xA]:
        return 1
    if opcode == 0xF:
        return 2
    if opcode == 0x3:
        return getAddress(cmd) + 1 # delay
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

def fixSRAMaddresses(mem, sram, device):
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
            address = device.params['SRAM_BLOCK0_LEN'] - len(sram[0])/4
            return (opcode << 20) + address
        elif opcode == 0xA:
            # SRAM end address
            address = device.params['SRAM_BLOCK0_LEN'] + len(sram[1])/4 + device.params['SRAM_DELAY_LEN'] * sram[2]
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
        return getAddress(cmd) if getOpcode(cmd) in [0x8, 0xA] else 0
    return max(addr(cmd) for cmd in cmds)

def timerCount(cmds):
    """Return the number of timer stops in a memory sequence.

    This should correspond to the number of timing results per
    repetition of the sequence.  Note that this method does no
    checking of the timer logic, for example whether every stop
    has a corresponding start.  That sort of checking is the
    user's responsibility at this point (if using the qubit server,
    these things are automatically checked).
    """
    return int(sum(np.asarray(cmds) == 0x400001)) # numpy version
    #return cmds.count(0x400001) # python list version
    

__server__ = FPGAServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
