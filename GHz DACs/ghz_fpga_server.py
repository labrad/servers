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

import struct
import time

import numpy as np

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T
from labrad.devices import DeviceWrapper, DeviceServer
from labrad.server import setting

import adc
import dac

NUM_PAGES = 2

REG_PACKET_LEN = 56

DAC_READBACK_LEN = 70

SRAM_LEN = 10240 #10240 words = 8192
SRAM_PAGE_LEN = 5120 #4096
SRAM_DELAY_LEN = 1024
SRAM_BLOCK0_LEN = 8192
SRAM_BLOCK1_LEN = 2048
SRAM_WRITE_PKT_LEN = 256 # number of words in each SRAM write packet
SRAM_WRITE_PAGES = SRAM_LEN / SRAM_WRITE_PKT_LEN # number of pages for writing SRAM

MASTER_SRAM_DELAY = 2 # microseconds for master to delay before SRAM to ensure synchronization

MEM_LEN = 512
MEM_PAGE_LEN = 256

TIMING_PACKET_LEN = 30

TIMEOUT_FACTOR = 10 # timing estimates are multiplied by this factor to determine sequence timeout

I2C_RB = 0x100
I2C_ACK = 0x200
I2C_RB_ACK = I2C_RB | I2C_ACK
I2C_END = 0x400

ADC_DEMOD_CHANNELS = 4
ADC_DEMOD_PACKET_LEN = 46 # length of result packets in demodulation mode
ADC_AVERAGE_PACKETS = 32 # number of packets that
ADC_AVERAGE_PACKET_LEN = 1024

ADC_TRIG_AMP = 255
ADC_REG_PACKET_LEN = 59
ADC_FILTER_LEN = 4096
ADC_SRAM_WRITE_PAGES = 9
ADC_SRAM_WRITE_LEN = 1024

# TODO: make sure paged operations (datataking) don't conflict with e.g. bringup
# - want to do this by having two modes for boards, either 'test' mode
#   (when a board does not belong to a board group) or 'production' mode
#   (when a board does belong to a board group).  It would be nice if boards
#   could be dynamically moved between groups, but we'll see about that...
# TODO: store memory and SRAM as numpy arrays, rather than lists and strings, respectively
# TODO: preflatten packets to reduce the send time
# TODO: run sequences to verify the daisy-chain order automatically
# TODO: when running adc boards in demodulation (streaming mode) it will be extremely important to check counters to verify that there is no packet loss


def littleEndian(data, bytes=4):
    return [(data >> ofs) & 0xFF for ofs in (0, 8, 16, 24)[:bytes]]

# functions to register packets for DAC boards

def regPing():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 1
    return regs    

def regDebug(word1, word2, word3, word4):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 2
    regs[1] = 1
    regs[13:17] = littleEndian(word1)
    regs[17:21] = littleEndian(word2)
    regs[21:25] = littleEndian(word3)
    regs[25:29] = littleEndian(word4)
    return regs
    
def regRunSram(startAddr, endAddr, loop=True, blockDelay=0, sync=249):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = (3 if loop else 4)
    regs[1] = 0
    regs[13:16] = littleEndian(startAddr, 3)
    regs[16:19] = littleEndian(endAddr-1 + SRAM_DELAY_LEN * blockDelay, 3)
    regs[19] = blockDelay
    regs[45] = sync
    return regs

def regClockPolarity(chan, invert):
    ofs = getCommand({'A': (4, 0), 'B': (5, 1)}, chan)
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 1
    regs[46] = (1 << ofs[0]) + ((invert & 1) << ofs[1])
    return regs

def regPllReset():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 1
    regs[46] = 0x80
    return regs

def regPllQuery():
    return regPing()

def regSerial(op, data):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 1
    regs[47] = op
    regs[48:51] = littleEndian(data, 3)
    return regs

def regI2C(data, read, ack):
    assert len(data) == len(read) == len(ack), "data, read and ack must have same length for I2C"
    assert len(data) <= 8, "Cannot send more than 8 I2C data bytes"
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 2
    regs[2] = 1 << (8 - len(data))
    regs[3] = sum(((r & 1) << (7 - i)) for i, r in enumerate(read))
    regs[4] = sum(((a & a) << (7 - i)) for i, a in enumerate(ack))
    regs[12:12-len(data):-1] = data
    return regs

def regRun(page, slave, delay, blockDelay=None, sync=249):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1 + (page << 7) # run memory in specified page
    regs[1] = 3 # stream timing data
    regs[13:15] = littleEndian(reps, 2)
    if blockDelay is not None:
        regs[19] = blockDelay # for boards running multi-block sequences
    regs[43] = int(slave)
    regs[44] = int(delay)
    regs[45] = sync
    return regs

def regIdle(delay):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0 # do not start
    regs[1] = 0 # no readback
    regs[43] = 3 # IDLE mode
    regs[44] = int(delay) # board delay
    return regs

def processReadback(resp):
    a = np.fromstring(resp, dtype='<u1')
    return {
        'build': a[51],
        'serDAC': a[56],
        'noPllLatch': (a[58] & 0x80) > 0,
        'ackoutI2C': a[61],
        'I2Cbytes': a[69:61:-1],
    }

def pktWriteSram(page, data):
    assert 0 <= page < SRAM_WRITE_PAGES, "SRAM page out of range: %d" % page 
    data = np.asarray(data)
    pkt = np.zeros(1026, dtype='<u1')
    pkt[0] = (page >> 0) & 0xFF
    pkt[1] = (page >> 8) & 0xFF
    pkt[2:2+len(data)*4:4] = (data >> 0) & 0xFF
    pkt[3:3+len(data)*4:4] = (data >> 8) & 0xFF
    pkt[4:4+len(data)*4:4] = (data >> 16) & 0xFF
    pkt[5:5+len(data)*4:4] = (data >> 24) & 0xFF
    #a, b, c, d = littleEndian(data)
    #pkt[2:2+len(data)*4:4] = a
    #pkt[3:3+len(data)*4:4] = b
    #pkt[4:4+len(data)*4:4] = c
    #pkt[5:5+len(data)*4:4] = d
    return pkt

def pktWriteMem(page, data):
    data = np.asarray(data)
    pkt = np.zeros(769, dtype='<u1')
    pkt[0] = page
    pkt[1:1+len(data)*3:3] = (data >> 0) & 0xFF
    pkt[2:2+len(data)*3:3] = (data >> 8) & 0xFF
    pkt[3:3+len(data)*3:3] = (data >> 16) & 0xFF
    #a, b, c = littleEndian(data, 3)
    #pkt[1:1+len(data)*3:3] = a
    #pkt[2:2+len(data)*3:3] = b
    #pkt[3:3+len(data)*3:3] = c
    return pkt


# functions to register packets for ADC boards

def regAdcPing():
    regs = np.zeros(ADC_REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs

def regAdcPllQuery():
    regs = np.zeros(ADC_REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs

def regAdcSerial(bits):
    regs = np.zeros(ADC_REG_PACKET_LEN, dtype='<u1')
    regs[0] = 6
    regs[3:6] = littleEndian(bits, 3)
    return regs

def regAdcRecalibrate():
    regs = np.zeros(ADC_REG_PACKET_LEN, dtype='<u1')
    regs[0] = 7
    return regs

def regAdcRun(mode, reps, filterFunc, filterStretchAt, filterStretchLen, demods):
    regs = np.zeros(ADC_REG_PACKET_LEN, dtype='<u1')
    regs[0] = mode # average mode, autostart
    regs[7:9] = littleEndian(reps, 2)
    
    regs[9:11] = littleEndian(len(filterFunc), 2)
    regs[11:13] = littleEndian(filterStretchAt, 2)
    regs[13:15] = littleEndian(filterStretchLen, 2)
    
    for i in range(ADC_DEMOD_CHANNELS):
        if i not in demods:
            continue
        addr = 15 + 4*i
        regs[addr:addr+2] = littleEndian(demods[i]['dphi'], 2)
        regs[addr+2:addr+4] = littleEndian(demods[i]['phi0'], 2)
    return regs


def processReadbackAdc(resp):
    a = np.fromstring(resp, dtype='<u1')
    return {
        'build': a[0],
        'noPllLatch': a[1] > 0,
    }

def pktWriteSramAdc(page, data):
    assert 0 <= page < ADC_SRAM_WRITE_PAGES, 'SRAM page out of range: %d' % page 
    data = np.asarray(data)
    pkt = np.zeros(1026, dtype='<u1')
    pkt[0:2] = littleEndian(page, 2)
    pkt[2:2+len(data)] = data
    return pkt


# device wrappers

class AdcDevice(DeviceWrapper):
    """Manages communication with a single GHz ADC board.
    
    All communication happens through the direct ehternet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @inlineCallbacks
    def connect(self, de, port, board, build, name):
        """Establish a connection to the board."""
        print 'connecting to ADC board: %s (build #%d)' % (adcMAC(board), build)

        self.server = de
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = adcMAC(board)
        self.devName = name
        self.serverName = de._labrad_name
        self.timeout = T.Value(1, 's')

        # set up our context with the ethernet server
        p = self.makePacket()
        p.connect(port)
        #p.require_length(70)
        # ADC boards send packets with different lengths:
        # - register readback: 46 bytes
        # - demodulator output: 48 bytes
        # - average readout: 1024 bytes
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()
    
    def makePacket(self):
        """Create a new packet to be sent to the ethernet server for this device."""
        return self.server.packet(context=self.ctx)
    
    def makeFilter(self, data, p):
        """Update a packet for the ethernet server with SRAM commands to upload the filter function."""
        for page in range(4):
            start = ADC_SRAM_WRITE_LEN * page
            end = start + ADC_SRAM_WRITE_LEN
            pkt = pktWriteSramAdc(page, data[start:end])
            p.write(pkt.tostring())
    
    def makeTrigLookups(self, demods, p):
        """Update a packet for the ethernet server with SRAM commands to upload Trig lookup tables."""
        page = 4
        channel = 0
        while channel < ADC_DEMOD_CHANNELS:
            data = []
            for ofs in [0, 1]:
                ch = channel + ofs
                for func in ['cosine', 'sine']:
                    if ch in demods:
                        d = demods[ch][func]
                    else:
                        d = np.zeros(256, dtype='<u1')
                    data.append(d)
            data = np.hstack(data)
            pkt = pktWriteSramAdc(page, data)
            p.write(pkt.tostring())            
            channel += 2 # two channels per sram packet
            page += 1 # each sram packet writes one page

    
    @inlineCallbacks
    def sendSRAM(self, filter, demods={}):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        yield p.send()
    
    
    @inlineCallbacks
    def sendRegisters(self, regs, readback=True):
        """Send a register packet and optionally readback the result.

        If readback is True, the result packet is returned as a string of bytes.
        """
        if not isinstance(regs, np.ndarray):
            regs = np.asarray(regs, dtype='<u1')
        p = self.makePacket()
        p.write(regs.tostring())
        if readback:
            p.read()
        ans = yield p.send()
        if readback:
            src, dst, eth, data = ans.read
            returnValue(data)
    
    @inlineCallbacks
    def runSerial(self, data):
        """Run a command or list of commands through the serial interface."""
        for d in listify(data):
            regs = regAdcSerial(data)
            yield self.sendRegisters(regs)
    
    @inlineCallbacks
    def recalibrate(self):
        regs = regAdcRecalibrate()
        yield self.sendRegisters(regs, readback=False)
    
    @inlineCallbacks
    def initPLL(self):
        yield self.runSerial([0x1FC093, 0x1FC092, 0x100004, 0x000C11])
        
    @inlineCallbacks
    def queryPLL(self):
        regs = regAdcPllQuery()
        r = yield self.sendRegisters(pkt)
        returnValue(processReadbackAdc(r)['noPllLatch'])
        
    @inlineCallbacks
    def runAverage(filterFunc, filterStretchLen, filterStretchAt, demods):
        # build registry packet
        regs = regAdcRun(2, 1, filterFunc, filterStretchLen, filterStretchAt, demods)

        # create packet for the ethernet server
        p = self.makePacket()
        self.makeFilter(filterFunc, p) # upload filter function
        self.makeTrigLookups(demods, p) # upload trig lookup tables
        p.write(regs.tostring()) # send registry packet
        p.timeout(T.Value(1, 's')) # set a conservative timeout
        p.read(ADC_AVERAGE_PACKETS) # read back all packets from average buffer
        
        ans = yield p.send()
                
        # parse the packets out and return data
        vals = []
        for src, dst, eth, data in ans.read:
            vals.append(np.fromstring(data, dtype='<i2'))
        IQs = np.hstack(vals).reshape(-1, 2)
        returnValue(IQs)
        
    
    @inlineCallbacks
    def runDemod(filterFunc, filterStretchLen, filterStretchAt, demods):
        # build registry packet
        regs = regAdcRun(4, 1, filterFunc, filterStretchLen, filterStretchAt, demods)

        # create packet for the ethernet server
        p = self.makePacket()
        self.makeFilter(filterFunc, p) # upload filter function
        self.makeTrigLookups(demods, p) # upload trig lookup tables
        p.write(regs.tostring()) # send registry packet
        p.timeout(T.Value(1, 's')) # set a conservative timeout
        p.read(1) # read back one demodulation packet
        
        ans = yield p.send()
                
        # parse the packets out and return data
        src, dst, eth, data = ans.read
        vals = np.fromstring(data[:44], dtype='<i2')
        IQs = vals.reshape(-1, 2)
        Irng, Qrng = [ord(i) for i in data[46:48]]
        twosComp = lambda i: i if i < 0x8 else i - 0x10
        Imax = twosComp((Irng >> 4) & 0xF) # << 12
        Imin = twosComp((Irng >> 0) & 0xF) # << 12
        Qmax = twosComp((Qrng >> 4) & 0xF) # << 12
        Qmin = twosComp((Qrng >> 0) & 0xF) # << 12
        returnValue((IQs, (Imax, Imin, Qmax, Qmin)))


class DacDevice(DeviceWrapper):
    """Manages communication with a single GHz DAC board.

    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @inlineCallbacks
    def connect(self, de, port, board, build, name):
        """Establish a connection to the board."""
        print 'connecting to DAC board: %s (build #%d)' % (dacMAC(board), build)

        self.server = de
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = dacMAC(board)
        self.devName = name
        self.serverName = de._labrad_name
        self.timeout = T.Value(1, 's')

        # set up our context with the ethernet server
        p = self.makePacket()
        p.connect(port)
        p.require_length(DAC_READBACK_LEN)
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
        writePage = page * SRAM_PAGE_LEN / SRAM_WRITE_PKT_LEN
        while len(data) > 0:
            chunk, data = data[:SRAM_WRITE_PKT_LEN*4], data[SRAM_WRITE_PKT_LEN*4:]
            chunk = np.fromstring(chunk, dtype='<u4')
            pkt = pktWriteSram(writePage, chunk)
            p.write(pkt.tostring())
            writePage += 1

    def makeMemory(self, data, p, page=0):
        """Update a packet for the ethernet server with Memory commands."""
        if len(data) > MEM_PAGE_LEN:
            msg = "Memory length %d exceeds maximum memory length %d (one page)."
            raise Exception(msg % (len(data), MEM_PAGE_LEN))
        # translate SRAM addresses for higher pages
        if page:
            data = shiftSRAM(data, page)
        pkt = pktWriteMem(page, data)
        p.write(pkt.tostring())

    def load(self, mem, sram, page=0):
        """Create a packet to write Memory and SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeMemory(mem, p, page=page)
        self.makeSRAM(sram, p, page=page)
        return p
    
    def collect(self, nPackets, timeout, triggerCtx):
        """Create a packet to collect data on the FPGA."""
        p = self.makePacket()
        p.timeout(T.Value(timeout, 's'))
        p.collect(nPackets)
        # note that if a timeout error occurs the remainder of the packet
        # is discarded, so that the trigger command will not be sent
        p.send_trigger(triggerCtx)
        return p
    
    def trigger(self, triggerCtx):
        """Create a packet to trigger the board group context."""
        return self.makePacket().send_trigger(triggerCtx)
    
    def read(self, nPackets):
        """Create a packet to read data from the FPGA."""
        return self.makePacket().read(nPackets)
            
    def discard(self, nPackets):
        """Create a packet to discard data on the FPGA."""
        return self.makePacket().discard(nPackets)

    def clear(self):
        """Create a packet to clear the ethernet buffer for this board."""
        return self.makePacket().clear()

    @inlineCallbacks
    def sendSRAM(self, data):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeSRAM(data, p)
        p.send()

#    @inlineCallbacks
#    def sendMemory(self, data):
#        """Write Memory data to the FPGA."""
#        p = self.makePacket()
#        self.makeMemory(data, p)
#        p.send()
#
#    @inlineCallbacks
#    def sendMemoryAndSRAM(self, mem, sram):
#        """Write both Memory and SRAM data to the FPGA."""
#        p = self.makePacket()
#        self.makeMemory(mem, p)
#        self.makeSRAM(sram, p)
#        p.send()

    @inlineCallbacks
    def sendRegisters(self, regs, readback=True):
        """Send a register packet and optionally readback the result.

        If readback is True, the result packet is returned as a string of bytes.
        """
        if not isinstance(regs, np.ndarray):
            regs = np.asarray(regs, dtype='<u1')
        p = self.makePacket()
        p.write(regs.tostring())
        if readback:
            p.read()
        ans = yield p.send()
        if readback:
            src, dst, eth, data = ans.read
            returnValue(data)

    @inlineCallbacks
    def runI2C(self, pkts):
        """Run I2C commands on the board."""
        answer = []
        for pkt in pkts:
            while len(pkt):
                data, pkt = pkt[:8], pkt[8:]
    
                bytes = [(b if b <= 0xFF else 0) for b in data]
                read = [b & I2C_RB for b in data]
                ack = [b & I2C_ACK for b in data]
                
                regs = regI2C(bytes, read, ack)
                r = yield self.sendRegisters(regs)
                ansBytes = processReadback(r)['I2Cbytes'][-len(data):] # readout data wrapped around to end
                
                answer += [b for b, r in zip(ansBytes, read) if r]
        returnValue(answer)

    @inlineCallbacks
    def runSerial(self, op, data):
        """Run a command or list of commands through the serial interface."""
        answer = []
        for d in listify(data):
            regs = regSerial(op, d)
            r = yield self.sendRegisters(regs)
            answer += [processReadback(r)['serDAC']]
        returnValue(answer)
        
    @inlineCallbacks
    def initPLL(self):
        yield self.runSerial(1, [0x1FC093, 0x1FC092, 0x100004, 0x000C11])
        pkt = regRunSram(0, 0, loop=False)
        yield self.sendRegisters(pkt, readback=False)
        
    @inlineCallbacks
    def queryPLL(self):
        regs = regPllQuery()
        r = yield self.sendRegisters(pkt)
        returnValue(processReadback(r)['noPllLatch'])


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
        self.fpgaServer = fpgaServer
    
    @inlineCallbacks
    def init(self, boards, delays):
        """Set up the direct ethernet server in our own context."""
        p = self.server.packet(context=self.ctx)
        p.connect(self.port)
        yield p.send()
        self.boardOrder = boards
        self.boardDelays = delays
    
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
        
        We clear the packet buffer for all boards, whether or not
        they succeeded.  In addition, we create a helpful message
        to return to the user, indicating which boards failed.
        """
        clearPkts = [d[0].clear() for d in devs]
        results = sorted((d[0].devName, r[0]) for d, r in zip(devs, collectResults))
        msgs = ['Some boards failed:']
        for n, s in results:
            msg = '%s: OK' if s else '%s: timeout!'
            msgs.append(msg % n)
        return clearPkts, '\n'.join(msgs)

    def makePackets(self, devs, timingOrder, page, reps, sync=249, multiBlockBoards=[]):
        """Make packets to run a sequence on this board group.

        Running a sequence has 4 stages:
        - Load memory and SRAM into all boards in parallel.
          If possible, this is done in the background using a separate
          page while another sequence is running.  We load in reverse
          order to ensure that all loads are done before starting.

        - Run sequence by firing a single packet that starts all boards.
          We start the master last, to ensure synchronization.

        - Collect timing data to ensure that the sequence is finished.
          We instruct the direct ethernet server to collect the packets
          but not send them yet.  Once collected, we can immediately run the
          next sequence if one was uploaded into the next page.

        - Read timing data.
          Having started the next sequence (if one was waiting) we now
          read the timing data collected by the direct ethernet server,
          process it and return it.

        This function prepares the LabRAD packets that will be sent for
        each of these steps, but does not actually send anything.
        """
        # dictionary of devices to be run
        deviceInfo = dict((dev[0].devName, dev) for dev in devs)
        
        # load memory and SRAM
        loadPkts = []
        for board in self.boardOrder:
            if board in deviceInfo:
                dev, mem, sram, slave, delay = deviceInfo[board]
                if not len(loadPkts):
                    # this will be the master, so add delays before SRAM
                    new_mem = []
                    cycles = int(MASTER_SRAM_DELAY * 25) & 0x0FFFFF
                    delay_cmd = 0x300000 + cycles
                    for cmd in mem:
                        if getOpcode(cmd) == 0xC: # call SRAM
                            new_mem.append(delay_cmd) # delay
                        new_mem.append(cmd)
                    mem = new_mem
                loadPkts.append(dev.load(mem, sram, page))
        
        # run all boards
        master = []
        slaves = []
        # send a run packet to each board in the board group, in the following order:
        # - slave and idle boards in daisy-chain order
        # - master board last
        for board, delay in zip(self.boardOrder, self.boardDelays):
            if board in deviceInfo:
                # this board will run
                dev, mem, sram, slave_dummy, delay_dummy = deviceInfo[board]
                slave = len(master) > 0 # the first board is master
                group = slaves if slave else master
                # check for boards running multi-block sequences
                if dev in multiBlockBoards:
                    if isinstance(delay_dummy, tuple):
                        delay_dummy, blockDelay = delay_dummy
                else:
                    blockDelay = None
                regs = regRun(page, slave, delay, blockDelay=blockDelay, sync=sync)
                group.append((dev.MAC, regs.tostring()))
            elif len(master):
                # this board is after the master, but will
                # not itself run, so we put it in idle mode
                regs = regIdle(delay)
                # look up the device wrapper for an arbitrary device in the board group
                dev = self.fpgaServer.devices[board]
                slaves.append((dev.MAC, regs.tostring()))
        data = slaves + master # send to the master board at the end
        runPkts = self.makeRunPackets(data)
        
        # collect and read (or discard) timing results
        collectPkts = []
        triggerPkts = []
        readPkts = []
        for dev, mem, sram, slave, delay in devs:
            nTimers = timerCount(mem)
            N = reps * nTimers / TIMING_PACKET_LEN
            seqTime = TIMEOUT_FACTOR * (sequenceTime(mem) * reps) + 1
            
            # if the collect times out (which can happen if a packet is dropped, for example)
            # we will have to send a trigger signal later to recover from the error, which
            # is why the trigger packet is created here. 
            collectPkts.append(dev.collect(N, seqTime, self.ctx))
            triggerPkts.append(dev.trigger(self.ctx))
            
            wantResults = timingOrder is None or dev.devName in timingOrder
            readPkts.append(dev.read(N) if wantResults else dev.discard(N))

        return loadPkts, runPkts, collectPkts, triggerPkts, readPkts

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
        
    def extractTiming(self, result):
        """Extract timing data coming back from a readPacket."""
        data = ''.join(data[3:63] for src, dst, eth, data in result.read)
        return np.fromstring(data, dtype='<u2')

    @inlineCallbacks
    def run(self, devs, reps, setupPkts, getTimingData, timingOrder, sync, setupState):
        """Run a sequence on this board group."""
        if not all((d[0].serverName == self.server._labrad_name) and
                   (d[0].port == self.port) for d in devs):
            raise Exception('All boards must belong to the same board group!')
        boardOrder = [d[0].devName for d in devs]

        # check whether this is a multiblock sequence
        multiBlockBoards = [dev for dev, mem, sram, slave, delay in devs
                                if isinstance(sram, tuple)]
        if len(multiBlockBoards):
            print 'Multi-block SRAM sequence'
            # update sram calls in memory sequences to the correct addresses
            def fixSRAM(dev):
                dev, mem, sram, slave, delay = dev
                mem = fixSRAMaddresses(mem, sram, dev)
                return dev, mem, sram, slave, delay
            devs = [fixSRAM(dev) for dev in devs]
            
            # pad sram blocks to take up full space (this will disable paging)
            def padSRAM(dev):
                dev, mem, sram, slave, delay = dev
                if isinstance(sram, tuple):
                    delay = (delay, sram[2])
                    sram = '\x00' * (SRAM_BLOCK0_LEN*4 - len(sram[0])) + sram[0] + sram[1]
                return dev, mem, sram, slave, delay
            devs = [padSRAM(dev) for dev in devs]
            
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
        loadPkts, runPkts, collectPkts, triggerPkts, readPkts = self.makePackets(
            devs, timingOrder, page, reps, sync, multiBlockBoards=multiBlockBoards)
        
        try:
            for pageLock in pageLocks:
                yield pageLock.acquire()

            # stage 1: load
            sendDone = sendAll(loadPkts, 'Load', boardOrder)
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
                        yield sendAll(setupPkts, 'Setup')
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
               
                # collect appropriate number of packets and then trigger other contexts
                collectAll = defer.DeferredList([p.send() for p in collectPkts], consumeErrors=True)
            finally:
                # note that if a timeout error occurs, the inter-context triggers in the
                # direct ethernet server are not actually sent, so that the next sequence
                # is here allowed to get in line to run, but their sequence will not execute
                # until after we clean up from the timeout and send the necessary triggers
                runLock.release()
            
            # wait for the collect packets
            results = yield collectAll
        finally:
            for pageLock in reversed(pageLocks):
                pageLock.release()
                
        if not all(success for success, result in results):
            # recover from timeout::
            # - clear any packets collected to this point on all boards
            # - send triggers to run context so that next sequence can execute
            # - record the error so we can keep track of how often timeouts happen
            
            # clear packets from all boards
            # FIXME: download packets here and process them, e.g. check counters
            clearPkts, msg = self.makeClearPackets(devs, results)
            yield sendAll(clearPkts, 'Timeout Recovery', boardOrder)
            
            # send trigger packets to unlock stuck device contexts
            for (success, result), triggerPkt in zip(results, triggerPkts):
                if not success:
                    yield triggerPkt.send()
                        
            readLock.release()
            raise TimeoutError(msg)
        
        # if we get to this point there was no timeout, so go ahead and read data
        readAll = sendAll(readPkts, 'Read', boardOrder)
        readLock.release()
        results = yield readAll # wait for read to complete

        if getTimingData:
            if timingOrder is not None:
                results = [results[boardOrder.index(b)] for b in timingOrder]
            if len(results):
                timing = np.vstack(self.extractTiming(r) for r in results)
            else:
                timing = []
            returnValue(timing)


class FPGAServer(DeviceServer):
    name = 'GHz DACs'
    retries = 5
    
    @inlineCallbacks
    def initServer(self):
        # load board group definitions from the registry
        # if the key does not exist, set it to an empty list
        p = self.client.registry.packet()
        p.cd(['', 'Servers', 'GHz DACs'], True)
        p.get('boardGroups', True, [], key='boardGroups')
        ans = yield p.send()
        self.boardGroupDefs = ans['boardGroups']
        self.boardGroups = {}
        # finish initializing the server
        yield DeviceServer.initServer(self)

    def initContext(self, c):
        c['daisy_chain'] = []
        c['start_delay'] = []
        c['timing_order'] = None
        c['master_sync'] = 249
        
        
    @inlineCallbacks
    def findDevices(self):
        # TODO: also look for ADC devices
        print 'Refreshing...'
        cxn = self.client
        yield cxn.refresh()
        found = []
        for name, server, port, boards, delays in self.boardGroupDefs:
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
                bg = self.boardGroups[server, port] = BoardGroup(self, de, port)
            else:
                bg = self.boardGroups[server, port]
            boards = ['%s FPGA %d' % (name, board) for board in boards]
            yield bg.init(boards, delays)

            # make a list of the boards currently known
            skips = {}
            for dname in self.devices:
                dev = self.devices[dname]
                if dev.serverName == de._labrad_name and dev.port == port:
                    skips[dev.board] = dev
            print 'Skipping:', sorted(skips.keys())

            p = de.packet()
            p.connect(port)
            p.require_length(DAC_READBACK_LEN)
            p.timeout(T.Value(1, 's'))
            
            for i in skips:
                # do not listen for packets from boards we want to skip
                p.reject_source_mac(dacMAC(i))
            
            p.listen()

            # ping all DAC boards
            for i in xrange(256):
                if i in skips:
                    found.append(skips[i].name)
                else:
                    p.destination_mac(dacMAC(i))
                    p.write(regPing().tostring())
            yield p.send(context=ctx)

            # get ID packets from DAC boards
            while True:
                try:
                    ans = yield de.read(context=ctx)
                    src, dst, eth, data = ans
                    info = processReadback(data)
                    board, build = int(src[-2:], 16), info['build']
                    devName = '%s DAC %d' % (name, board)
                    args = de, port, board, build, devName
                    found.append((devName, args))
                except T.Error:
                    break

            # ping all ADC boards
            for i in xrange(256):
                if i in skips:
                    found.append(skips[i].name)
                else:
                    p.destination_mac(adcMAC(i))
                    p.write(regAdcPing().tostring())
            yield p.send(context=ctx)

            # get ID packets from ADC boards
            while True:
                try:
                    ans = yield de.read(context=ctx)
                    src, dst, eth, data = ans
                    info = processReadbackAdc(data)
                    board, build = int(src[-2:], 16), info['build']
                    devName = '%s ADC %d' % (name, board)
                    args = de, port, board, build, devName
                    found.append((devName, args))
                except T.Error:
                    break

            # expire this context to stop listening
            yield cxn.manager.expire_context(de.ID, context=ctx)
        returnValue(found)

    def deviceWrapper(self, *a, **kw):
        """Build a DAC or ADC device wrapper, depending on the device name"""
        name = a[-1]
        if 'ADC' in name:
            return AdcDevice(*a, **kw)
        else:
            return DacDevice(*a, **kw)


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


    ## remote settings

    @setting(20, 'SRAM Address', addr='w', returns='w')
    def sram_address(self, c, addr=None):
        """Sets the next SRAM address to be written to by SRAM."""
        #raise Exception('SRAM Address is deprecated!  Please upload your entire sequence at once.')
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        d['sramAddress'] = addr*4
        return addr


    @setting(21, 'SRAM', data=['*w: SRAM Words to be written', 's: Raw SRAM data'],
                         returns='')
    def sram(self, c, data):
        """Writes data to the SRAM at the current starting address.
        
        Data can be specified as a list of 32-bit words, or a pre-flattened byte string.
        """
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        addr = d.setdefault('sramAddress', 0)
        if 'sram' in d:
            sram = d['sram']
            if isinstance(sram, tuple):
                # last sequence was multiblock
                # clear the sram
                sram = ''
                addr = d['sramAddress'] = 0
        else:
            sram = '\x00' * addr
        if not isinstance(data, str):
            data = data.asarray.tostring()
        #d['sram'] = data
        d['sram'] = sram[0:addr] + data + sram[addr+len(data):]
        d['sramAddress'] += len(data)
        #return addr/4, len(data)/4


    @setting(22, 'SRAM dual block',
             block1=['*w: SRAM Words to be written', 's: Raw SRAM data'],
             block2=['*w: SRAM Words for second block', 's: Raw SRAM for second block'],
             delay='w: nanoseconds to delay',
             returns='')
    def sram2(self, c, block1, block2, delay):
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


    @setting(31, 'Memory', data='*w: Memory Words to be written',
                           returns='')
    def memory(self, c, data):
        """Writes data to the Memory at the current starting address."""
        dev = self.selectedDAC(c)
        d = c.setdefault(dev, {})
        d['mem'] = data


    @setting(40, 'Run Sequence', reps='w', getTimingData='b',
                                 setupPkts='?{(((ww), s, ((s?)(s?)(s?)...))...)}',
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
        
        if len(c['daisy_chain']):
            # run multiple boards, with first board as master
            devs = [self.getDevice(c, n) for n in c['daisy_chain']]
            delays = c['start_delay']
            delays = [0]*len(c['daisy_chain'])
        else:
            # run the selected device only
            devs = [self.selectedDAC(c)]
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
                # FIXME: check that it is okay to rerun this function call, since some data can get mutated
                ans = yield bg.run(devices, reps, setupReqs, getTimingData, timingOrder, c['master_sync'], set(setupState))
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
    
    
    @setting(42, 'Daisy Chain', boards='*s', returns='*s')
    def daisy_chain(self, c, boards=None):
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

    @setting(43, 'Start Delay', delays='*w', returns='*w')
    def start_delay(self, c, delays=None):
        """Set start delays in ns for SRAM in the daisy chain.

        DEPRECATED: start delays are now handled automatically by the
        GHz DACs server, as configured in the registry for each board group.
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

    @setting(49, 'Performance Data', returns='*((sw)(*v, *v, *v, *v, *v))')
    def performance_data(self, c):
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


    @setting(50, 'Debug Output', data='(wwww)', returns='')
    def debug_output(self, c, data):
        """Outputs data directly to the output bus. (DAC only)"""
        dev = self.selectedDAC(c)
        pkt = regDebug(*data)
        yield dev.sendRegisters(pkt)


    @setting(51, 'Run SRAM', data='*w', loop='b', blockDelay='w', returns='')
    def run_sram(self, c, data, loop=False, blockDelay=0):
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


    @setting(100, 'I2C', data='*w', returns='*w')
    def i2c(self, c, data):
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


    @setting(110, 'LEDs', data=['w', '(bbbbbbbb)'], returns='w')
    def leds(self, c, data):
        """Sets the status of the 8 I2C LEDs. (DAC only)"""
        dev = self.selectedDAC(c)

        if isinstance(data, tuple):
            # convert to a list of digits, and interpret as binary int
            data = long(''.join(str(int(b)) for b in data), 2)

        pkts = [[200, 68, data & 0xFF]] # 192 for build 1
        yield dev.runI2C(pkts)  
        returnValue(data)


    @setting(120, 'Reset Phasor', returns='b: phase detector output')
    def reset_phasor(self, c):
        """Resets the clock phasor. (DAC only)"""
        dev = self.selectedDAC(c)

        pkts = [[152,   0, 127, 0],  # set I to 0 deg
                [152,  34, 254, 0],  # set Q to 0 deg
                [112,  65],          # set enable bit high
                [112, 193],          # set reset high
                [112,  65],          # set reset low
                [112,   1],          # set enable low
                [113, I2C_RB]]       # read phase detector

        r = yield dev.runI2C(pkts)
        returnValue((r[0] & 1) > 0)


    @setting(121, 'Set Phasor',
                  data=[': poll phase detector only',
                        'v[rad]: set angle (in rad, deg, \xF8, \', or ")'],
                  returns='b: phase detector output')
    def set_phasor(self, c, data=None):
        """Sets the clock phasor angle and reads the phase detector bit. (DAC only)"""
        dev = self.selectedDAC(c)

        if data is None:
            pkts = [[112,  1], [113, I2C_RB]]
        else:
            sn = int(round(127 + 127*np.sin(data))) & 0xFF
            cs = int(round(127 + 127*np.cos(data))) & 0xFF
            pkts = [[152,  0, sn, 0],
                    [152, 34, cs, 0],
                    [112,  1],
                    [113, I2C_RB]]
                   
        r = yield dev.runI2C(pkts)
        returnValue((r[0] & 1) > 0)

    @setting(130, 'Vout', chan='s', V='v[V]', returns='w')
    def vout(self, c, chan, V):
        """Sets the output voltage of any Vout channel, A, B, C or D. (DAC only)"""
        cmd = getCommand({'A': 16, 'B': 18, 'C': 20, 'D': 22}, chan)
        dev = self.selectedDAC(c)
        val = int(max(min(round(V*0x3333), 0x10000), 0))
        pkts = [[154, cmd, (val >> 8) & 0xFF, val & 0xFF]]
        yield dev.runI2C(pkts)
        returnValue(val)
        

    @setting(135, 'Ain', returns='v[V]')
    def ain(self, c):
        """Reads the voltage on Ain. (DAC only)"""
        dev = self.selectedDAC(c)
        pkts = [[144, 0], [145, I2C_RB_ACK, I2C_RB]]
        r = yield dev.runI2C(pkts)
        returnValue(T.Value(((r[0] << 8) + r[1]) / 819.0, 'V'))


    @setting(200, 'PLL', data=['w', '*w'], returns='*w')
    def pll(self, c, data):
        """Sends a command or a sequence of commands to the PLL. (DAC only)

        The returned WordList contains any read-back values.
        It has the same length as the sent list.
        """
        dev = self.selectedDAC(c)
        return dev.runSerial(1, data)

    @setting(204, 'DAC', chan='s', data=['w', '*w'], returns='*w')
    def dac_cmd(self, c, chan, data):
        """Send a command or sequence of commands to either DAC. (DAC only)

        The DAC channel must be either 'A' or 'B'.
        The returned list of words contains any read-back values.
        It has the same length as the sent list.
        """
        cmd = getCommand({'A': 2, 'B': 3}, chan)
        dev = self.selectedDAC(c)
        return dev.runSerial(cmd, data)


    @setting(206, 'DAC Clock Polarity', chan='s', invert='b', returns='b')
    def dac_pol(self, c, chan, invert):
        """Sets the clock polarity for either DAC. (DAC only)"""
        regs = regClockPolarity(chan, invert)
        dev = self.selectedDAC(c)
        yield dev.sendRegisters(regs)
        returnValue(invert)


    @setting(210, 'PLL Init', returns='')
    def init_pll(self, c, data):
        """Sends the initialization sequence to the PLL. (DAC and ADC)

        The sequence is [0x1FC093, 0x1FC092, 0x100004, 0x000C11].
        """
        dev = self.selectedDevice(c)
        yield dev.initPLL()


    @setting(211, 'PLL Reset', returns='')
    def pll_reset(self, c):
        """Resets the FPGA internal GHz serializer PLLs. (DAC only)"""
        dev = self.selectedDAC(c)
        regs = regPllReset()
        yield dev.sendRegisters(regs)

    @setting(212, 'PLL Query', returns='b')
    def pll_query(self, c):
        """Checks the FPGA internal GHz serializer PLLs for lock failures. (DAC and ADC)

        Returns T if any of the PLLs have lost lock since the last reset.
        """
        dev = self.selectedDevice(c)
        unlocked = yield dev.queryPLL()
        returnValue(unlocked)


    @setting(220, 'DAC Init', chan='s', signed='b', returns='b')
    def init_dac(self, c, chan, signed=False):
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


    @setting(221, 'DAC LVDS', chan='s', data='w', returns='(www*(bb))')
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


    @setting(225, 'DAC BIST', chan='s', data='*w', returns='(b(ww)(ww)(ww))')
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



    @setting(500, 'ADC Recalibrate', returns='')
    def adc_recalibrate(self, c):
        """Recalibrate the analog-to-digital converters. (ADC only)"""
        dev = self.selectedADC(c)
        yield dev.recalibrate()
        
    @setting(501, 'ADC Filter Func', bytes='s', stretchLen='w', stretchAt='w', returns='')
    def adc_filter_func(self, c, bytes, stretchLen=0, stretchAt=0):
        """Set the filter function to be used with the selected ADC board. (ADC only)
        
        Each byte specifies the filter weight for a 4ns interval.  In addition,
        you can specify a stretch which will repeat a value in the middle of the filter
        for the specified length (in 4ns intervals).
        """
        assert len(bytes) <= ADC_FILTER_LEN, 'Filter function max length is %d' % ADC_FILTER_LEN
        dev = self.selectedADC(c)
        bytes = np.fromstring(bytes, dtype='<u1')
        d = c.setdefault(dev, {})
        d['filterFunc'] = bytes
        d['filterStretchLen'] = stretchLen
        d['filterStretchAt'] = stretchAt
        
    @setting(502, 'ADC Trig Magnitude', channel='w', sineAmp='w', cosineAmp='w', returns='')
    def adc_trig_magnitude(self, c, channel, sineAmp, cosineAmp):
        """Set the magnitude of sine and cosine functions for a demodulation channel. (ADC only)
        
        The channel indicates which demodulation channel to use, in the range 0 to N-1 where
        N is the number of channels (currently 4).  sineAmp and cosineAmp are the magnitudes
        of the respective sine and cosine functions, ranging from 0 to 255.
        """
        assert 0 <= channel < ADC_DEMOD_CHANNELS, 'channel out of range: %d' % channel
        assert 0 <= sineAmp <= ADC_TRIG_AMP, 'sine amplitude out of range: %d' % sineAmp
        assert 0 <= cosineAmp <= ADC_TRIG_AMP, 'cosine amplitude out of range: %d' % cosineAmp
        dev = self.selectedADC(c)
        d = c.setdefault(dev, {})
        ch = d.setdefault(channel, {})
        ch['sineAmp'] = sineAmp
        ch['cosineAmp'] = cosineAmp
        phi = np.pi/2 * (np.arange(256) + 0.5) / 256
        ch['sine'] = np.floor(sineAmp * np.sin(phi) + 0.5).astype('uint8')
        ch['cosine'] = np.floor(cosineAmp * np.cos(phi) + 0.5).astype('uint8')
    
    @setting(503, 'ADC Demod Phase', channel='w', dphi='i', phi0='i', returns='')
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
    
    @setting(600, 'ADC Run Average', returns='*(i{I} i{Q})')
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
        demods = dict((i, info[i]) for i in range(ADC_DEMOD_CHANNELS) if i in info)
        ans = yield dev.runAverage(filterFunc, filterStretchLen, filterStretchAt, demods)
        returnValue(ans)
    
    @setting(601, 'ADC Run Demod', returns='*(i{I} i{Q}), (i{Imax} i{Imin} i{Qmax} i{Qmin})')
    def adc_run_demod(self, c, channel, sineAmp, cosineAmp):
        dev = self.selectedADC(c)
        info = c.setdefault(dev, {})
        filterFunc = info.get('filterFunc', np.array([255], dtype='<u1'))
        filterStretchLen = info.get('filterStretchLen', 0)
        filterStretchAt = info.get('filterStretchAt', 0)
        demods = dict((i, info[i]) for i in range(ADC_DEMOD_CHANNELS) if i in info)
        ans = yield dev.runDemod(filterFunc, filterStretchLen, filterStretchAt, demods)
        returnValue(ans)
    
    # TODO: new settings
    # - run ADC board in average mode
    # - run ADC board in demodulation mode
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

def dacMAC(board):
    """Get the MAC address of a DAC board as a string."""
    return '00:01:CA:AA:00:' + ('0'+hex(int(board))[2:])[-2:].upper()

def adcMAC(board):
    """Get the MAC address of an ADC board as a string."""
    return '00:01:CA:AA:01:' + ('0'+hex(int(board))[2:])[-2:].upper()

def listify(data):
    """Ensure that a piece of data is a list."""
    return data if isinstance(data, list) else [data]


# commands for analyzing and manipulating FPGA memory sequences

# TODO: need to incorporate SRAMoffset when calculating sequence time 
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
        return 25*12 # maximum SRAM length is 12us, with 25 cycles per us

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

def fixSRAMaddresses(mem, sram, dev):
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
    

__server__ = FPGAServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
