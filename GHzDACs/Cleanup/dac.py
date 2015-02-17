import numpy as np

from ...GHzDACs import jumpTable
from ..Cleanup import fpga
# import servers.GHzDACs.Cleanup.fpga as fpga
# import servers.GHzDACs.jumpTable as jumpTable

# named functions
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from ..util import littleEndian, TimedLock
# from servers.GHzDACs.util import littleEndian, TimedLock


# CHANGELOG
#
# 2012 September 27 - Daniel Sank
#
# Register readback bytes 52, 53 (zero indexed) are SRAM counter bytes
# as of build V7 build 11. I have modified processReadback accordingly.
# Note that no functionality was lost in this change because those
# readback bytes weren't being used. The documentation on the GHzDAC
# notes that they used to be for memory checksum, but no longer.
#
# 2011 November 16 - Daniel Sank
#
# Changed params->buildParams and reworked the way boardParams gets stored.
# See corresponding notes in ghz_fpga_server.py
#
# 2011 February 9 - Daniel Sank
# Removed almost all references to hardcoded hardware parameters, for example
# the various SRAM lengths. These values are now board specific and loaded by
# DacDevice.connect().


# +DOCUMENTATION
#
# ++SRAM NOMENCLATURE
# The word "page" used to be overloaded. An SRAM "page" referred to a chunk of
# 256 SRAM words written by one ethernet packet, AND to a unit of SRAM used
# for simultaneous execution/download operation. In the FPGA server coding we
# now use "page" to refer to a section of the physical SRAM used in a
# sequence, where we have two pages to allow for simultaneous execution and
# download of next sequence. We now call a group of 256 SRAM words written by
# an ethernet packet a "derp"
#
# ++REGISTRY KEYS
# dacBuildN: *(s?), [(parameterName, value),...]
# Each build of the FPGA code has a build number. We use this build number to
# determine the hardware parameters for each board. Hardware parameters are:
# SRAM_LEN - The length, in SRAM words, of the total SRAM memory
#   SRAM_PAGE_LEN - Size, in words, of one page of SRAM. See definition above
#                   The value of this key is typically SRAM_LEN/2.
#   SRAM_DELAY_LEN - Number of clock cycles of repetition of the end of SRAM
#                    Block0 is this number times the value in register[19]
#   SRAM_BLOCK0_LEN - Length, in words, of the first block of SRAM.
#   SRAM_BLOCK1_LEN - Length, in words, of the second block of SRAM.
#   SRAM_WRITE_PKT_LEN - Number of words written per SRAM write packet, ie.
#                        words per derp.
# dacN: *(s?), [(parameterName, value),...]
# There are parameters which may be specific to each individual board. These
# parameters are:
#   fifoCounter - FIFO counter necessary for the appropriate clock delay
#   lvdsSD - LVDS SD necessary for the appropriate clock delay

# TODO
# Think of better variable names than self.params and self.boardParams


# functions to register packets for DAC boards
# These functions generate numpy arrays of bytes which will be converted
# to raw byte strings prior to being sent to the direct ethernet server.

# Time for master to delay before SRAM to ensure synchronization
MASTER_SRAM_DELAY = 2  #us


class DAC(fpga.FPGA):
    MAC_PREFIX = '00:01:CA:AA:00:'
    REG_PACKET_LEN = 56
    READBACK_LEN = 70

    TIMING_PACKET_LEN = 30

    # Master delay before SRAM to ensure synchronization
    MASTER_SRAM_DELAY = 2  # microseconds

    @classmethod
    def macFor(cls, board):
        """Get the MAC address of a DAC board as a string."""
        return cls.MAC_PREFIX + ('0' + hex(int(board))[2:])[-2:].upper()

    @classmethod
    def isMac(mac):
        """Return True if this mac is for a DAC, otherwise False"""
        return mac.startswith('00:01:CA:AA:00:')

    # lifecycle methods

    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """Establish a connection to the board."""
        print('connecting to DAC board: %s (build #%d)' % \
              (self.macFor(board), build))

        self.boardGroup = group
        self.server = de
        self.cxn = de._cxn
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = self.macFor(board)
        self.devName = name
        self.serverName = de._labrad_name
        self.timeout = T.Value(1, 's')

        # Set up our context with the ethernet server
        # This context is expired when the device shuts down
        p = self.makePacket()
        p.connect(port)
        p.require_length(self.READBACK_LEN)
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()

        # Get board specific information about this device.
        # We talk to the labrad system using a new context and close it when
        # done.
        reg = self.cxn.registry
        ctxt = reg.context()
        p = reg.packet()
        p.cd(['', 'Servers', 'GHz FPGAs'])
        p.get('dac' + self.devName.split(' ')[-1], key='boardParams')
        try:
            resp = yield p.send()
            boardParams = resp['boardParams']
            self.parseBoardParameters(boardParams)
        finally:
            yield self.cxn.manager.expire_context(reg.ID, context=ctxt)

    @inlineCallbacks
    def shutdown(self):
        """Called when this device is to be shutdown."""
        yield self.cxn.manager.expire_context(self.server.ID,
                                              context=self.ctx)

    # Register byte methods

    @classmethod
    def regPing(cls):
        """Returns a numpy array of register bytes to ping DAC register"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0  # No sequence start
        regs[1] = 1  # Readback after 2us
        return regs

    @classmethod
    def regPllQuery(cls):
        """Returns a numpy array of register bytes to query PLL status"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1  # No sequence start
        regs[1] = 1  # Readback after 2us
        return regs

    @classmethod
    def regSerial(cls, op, data):
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0  # Start mode = no start
        regs[1] = 1  # Readback = readback after 2us to allow for serial
        regs[47] = op  # Set serial operation mode to op
        regs[48:51] = littleEndian(data, 3)  # Serial data
        return regs

    @classmethod
    def regPllReset(cls):
        """Send reset pulse to 1GHz PLL"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0
        regs[1] = 1
        regs[46] = 0x80  #Set d[7..0] to 10000000 = reset 1GHz PLL pulse
        return regs

    def resetPLL(self):
        """Reset PLL"""
        raise NotImplementedError

    # Methods to get byte arrays to be written to the board

    @classmethod
    def pktWriteSram(cls, derp, data):
        """A DAC packet to write one derp of SRAM
        
        This function converts an array of SRAM words into a byte string
        appropriate for writing over ethernet to the board.
        
        A derp is 256 words of SRAM, 1024 bytes
        
        derp - int: Which derp to write, ie address in SRAM
        data - ndarray: array of SRAM words in <u4 format.
               Maximum length is SRAM_WRITE_PKT_LEN words, ie one derp.
               As of build 7 this is 256 words.
               If less than a full derp is written, the rest of the derp is
               populated with zeros.
        """
        assert 0 <= derp < cls.SRAM_WRITE_DERPS, \
            "SRAM derp out of range: %d" % derp
        assert 0 < len(data) <= cls.SRAM_WRITE_PKT_LEN, \
            "Tried to write %d words to SRAM derp" % len(data)
        data = np.asarray(data)
        # Packet length is data length plus two bytes for write address (derp)
        pkt = np.zeros(1026, dtype='<u1')
        # DAC firmware assumes SRAM write address lowest 8 bits = 0, so here
        # we're only setting the middle and high byte. This is good, because
        # it means that each time we increment derp by 1, we increment our
        # SRAM write address by 256, ie. one derp.
        pkt[0] = (derp >> 0) & 0xFF
        pkt[1] = (derp >> 8) & 0xFF
        # Each sram word is four bytes long
        # Our data as coming from makeSram is a np array of 4 byte integers
        # with low bytes first. Because of this you would think that
        # (data>>24)&0xFF is the least significant bytes. However, python
        # thinks for you, and it turns out that data>>24 is the most
        # significant byte. Go figure. The DAC expects the data with
        # least significant byte first in each word.
        # Note that if len(data)<SRAM_WRITE_PKT_LEN, ie. smaller than a full
        # derp, we only take as much data as actually exists.

        pkt[2:2 + len(data) * 4:4] = (data >> 0) & 0xFF  #Least sig. byte
        pkt[3:3 + len(data) * 4:4] = (data >> 8) & 0xFF
        pkt[4:4 + len(data) * 4:4] = (data >> 16) & 0xFF
        pkt[5:5 + len(data) * 4:4] = (data >> 24) & 0xFF  #Most sig. byte
        #a, b, c, d = littleEndian(data)
        #pkt[2:2+len(data)*4:4] = a
        #pkt[3:3+len(data)*4:4] = b
        #pkt[4:4+len(data)*4:4] = c
        #pkt[5:5+len(data)*4:4] = d
        return pkt

    @classmethod
    def pktWriteMem(cls, page, data):
        data = np.asarray(data)
        pkt = np.zeros(769, dtype='<u1')
        pkt[0] = page
        pkt[1:1 + len(data) * 3:3] = (data >> 0) & 0xFF
        pkt[2:2 + len(data) * 3:3] = (data >> 8) & 0xFF
        pkt[3:3 + len(data) * 3:3] = (data >> 16) & 0xFF
        #a, b, c = littleEndian(data, 3)
        #pkt[1:1+len(data)*3:3] = a
        #pkt[2:2+len(data)*3:3] = b
        #pkt[3:3+len(data)*3:3] = c
        return pkt

    # Utility

    @staticmethod
    def readback2BuildNumber(resp):
        """Get build number from register readback"""
        a = np.fromstring(resp, dtype='<u1')
        return a[51]

    def parseBoardParameters(self, parametersFromRegistry):
        """Handle board specific data retreived from registry"""
        self.boardParams = dict(parametersFromRegistry)
        #for key, val in dict(parametersFromRegistry).items():
        #    setattr(self, key, val)

    @staticmethod
    def bistChecksum(data):
        bist = [0, 0]
        for i in xrange(0, len(data), 2):
            for j in xrange(2):
                if data[i + j] & 0x3FFF != 0:
                    bist[j] = (((bist[j] << 1) & 0xFFFFFFFE) | \
                               ((bist[j] >> 31) & 1)) ^ \
                              ((data[i + j] ^ 0x3FFF) & 0x3FFF)
        return bist

    @classmethod
    def shiftSRAM(cls, cmds, page):
        """Shift the addresses of SRAM calls for different pages.

        Takes a list of memory commands and a page number and
        modifies the commands for calling SRAM to point to the
        appropriate page.
        """

        def shiftAddr(cmd):
            opcode, address = MemorySequence.getOpcode(cmd), \
                              MemorySequence.getAddress(cmd)
            if opcode in [0x8, 0xA]:
                address += page * cls.SRAM_PAGE_LEN
                return (opcode << 20) + address
            else:
                return cmd

        return [shiftAddr(cmd) for cmd in cmds]

    @staticmethod
    def getCommand(cmds, chan):
        """Get a command from a dictionary of commands.

        Raises a helpful error message if the given channel is not allowed.
        """
        try:
            return cmds[chan]
        except:
            raise Exception("Allowed channels are %s." % sorted(cmds.keys()))


class DacRunner(object):
    pass


class DacRunner_Build7(DacRunner):
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
            # Why is there a factor of 4 here? Is this because each SRAM
            # word is 4 bytes? Check John's documentation
            self.sram = self.sram[:self.dev.SRAM_PAGE_LEN * 4]

        # calculate expected number of packets
        self.nTimers = MemorySequence.timerCount(self.mem)
        self.nPackets = self.reps * self.nTimers // DAC.TIMING_PACKET_LEN
        # calculate sequence time
        self.memTime = MemorySequence.sequenceTime_sec(self.mem)
        # Why is this +1 here?
        self.seqTime = fpga.TIMEOUT_FACTOR * (self.memTime * self.reps) + 1

    def pageable(self):
        """
        Check whether sequence fits in one page, based on SRAM addresses
        called by mem commands.
        """
        return maxSRAM(self.mem) <= self.dev.SRAM_PAGE_LEN

    def _fixDualBlockSram(self):
        """
        If this sequence is for dual-block sram, fix memory addresses and
        build sram.
        
        When this function completes
          1. self.sram will be a byte string to be written to the
             physical memory block
          2. self.blockDelay will be an integer, the number of times
             to repeate the delay block
          3. The memory sequence is adjusted so that SRAM start addr
             and SRAM end addr are set to properly execute the dual
             blocks of SRAM.
        
        Input:
              Block0            Block1
              aaaaaaaaaaaaaDELAYbbbbbb
        Output:
        |00000aaaaaaaaaaaaa|bbbbbb
        
        The sram byte string is prepended with zeros to make sure that
        our desired block0, represented by a's, lies with its end
        exactly at the end of the physical memory block0. The two blocks
        are concatened forming a single byte string.
        
        Note that because the sram sequence will be padded to take up the
        entire first block of SRAM (before the delay section), this
        disables paging.
        """
        #Note that as this function executes self.sram should be a tuple of
        #(block0,block1,delay) where block0 and block1 are strings
        if isinstance(self.sram, tuple):
            # update addresses in memory commands that call into SRAM
            self.mem = MemorySequence.fixSRAMaddresses(self.mem, self.sram, self.dev)

            # combine blocks into one sram sequence to be uploaded
            block0, block1, delayBlocks = self.sram
            #Prepend bloock0 with \x00's so that the actual signal data
            #exactly fills the first physical SRAM block
            #Note block0 length in bytes = 4*block0 length in words
            data = '\x00' * (self.dev.SRAM_BLOCK0_LEN * 4 - \
                             len(block0)) + block0 + block1
            self.sram = data
            self.blockDelay = delayBlocks

    def loadPacket(self, page, isMaster):
        """Create pipelined load packet.  For DAC, upload mem and SRAM."""
        if isMaster:
            # this will be the master, so add delays before SRAM
            self.mem = MemorySequence.addMasterDelay(self.mem)
            # Recompute sequence time
            # Recalculate sequence time
            self.memTime = MemorySequence.sequenceTime_sec(self.mem)
            # Following line added Oct 2 2012 - DTS
            self.seqTime = fpga.TIMEOUT_FACTOR * (self.memTime * self.reps) + 1
        return self.dev.load(self.mem, self.sram, page)

    def setupPacket(self):
        """Create non-pipelined setup packet.  For DAC, does nothing."""
        return None

    def runPacket(self, page, slave, delay, sync):
        """Create run packet."""
        startDelay = self.startDelay + delay
        regs = self.dev.regRun(self.reps, page, slave, startDelay,
                               blockDelay=self.blockDelay, sync=sync)
        return regs

    def collectPacket(self, seqTime, ctx):
        """
        Collect appropriate number of ethernet packets for this sequence, then
        trigger the run context.
        """
        return self.dev.collect(self.nPackets, seqTime, ctx)

    def triggerPacket(self, ctx):
        """Send a trigger to the master context"""
        return self.dev.trigger(ctx)

    def readPacket(self, timingOrder):
        """
        Read (or discard) appropriate number of ethernet packets, depending
        on whether timing results are wanted.
        """
        keep = any(s.startswith(self.dev.devName) for s in timingOrder)
        return self.dev.read(self.nPackets) if keep else \
            self.dev.discard(self.nPackets)

    def extract(self, packets):
        """Extract timing data coming back from a readPacket."""
        data = ''.join(data[3:63] for data in packets)
        return np.fromstring(data, dtype='<u2').astype('u4')


class DAC_Build7(DAC):
    """Manages communication with a single GHz DAC board.

    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """

    RUNNER_CLASS = DacRunner_Build7

    MEM_LEN = 512
    MEM_PAGE_LEN = 256
    # timing estimates are multiplied by this factor to determine sequence
    # timeout
    I2C_RB = 0x100
    I2C_ACK = 0x200
    I2C_RB_ACK = I2C_RB | I2C_ACK
    I2C_END = 0x400
    MAX_FIFO_TRIES = 5

    SRAM_LEN = 10240
    SRAM_WRITE_PKT_LEN = 256
    SRAM_WRITE_DERPS = SRAM_LEN // SRAM_WRITE_PKT_LEN
    SRAM_PAGE_LEN = 5120
    SRAM_DELAY_LEN = 1024
    SRAM_BLOCK0_LEN = 8192
    SRAM_BLOCK1_LEN = 2048

    # Methods to get bytes to be written to register

    def buildRunner(self, reps, info):
        """Get a runner for this board"""
        mem = info.get('mem', None)
        startDelay = info.get('startDelay', 0)
        sram = info.get('sram', None)
        runner = self.RUNNER_CLASS(self, reps, startDelay, mem, sram)
        return runner

    @classmethod
    def regRun(cls, reps, page, slave, delay, blockDelay=None, sync=249):
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1 + (page << 7)  # run memory in specified page
        regs[1] = 3  # stream timing data
        regs[13:15] = littleEndian(reps, 2)
        if blockDelay is not None:
            regs[19] = blockDelay  # for boards running multi-block sequences
        regs[43] = int(slave)
        # Addressing out of order because we added the high byte for start
        # delay after the rest of the registers had been defined.
        regs[44], regs[51] = littleEndian(int(delay), 2)
        regs[45] = sync
        return regs

    @classmethod
    def regRunSram(cls, startAddr, endAddr, loop=True, blockDelay=0, sync=249):
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = (3 if loop else 4)  #3: continuous, 4: single run
        regs[1] = 0  #No register readback
        regs[13:16] = littleEndian(startAddr, 3)  #SRAM start address
        regs[16:19] = littleEndian(endAddr - 1 + cls.SRAM_DELAY_LEN \
                                   * blockDelay, 3)  #SRAM end
        regs[19] = blockDelay
        regs[45] = sync
        return regs

    @classmethod
    def regIdle(cls, delay):
        """
        Numpy array of register bytes for idle mode
        
        TODO: Move into DAC superclass if this is common functionality.
              Need to check.
        """
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0  # do not start
        regs[1] = 0  # no readback
        regs[43] = 3  # IDLE mode
        # 1 August 2012: Why do we need delays when in idle mode? DTS
        regs[44] = int(delay)
        return regs

    @classmethod
    def regClockPolarity(cls, chan, invert):
        ofs = {'A': (4, 0), 'B': (5, 1)}[chan]
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0
        regs[1] = 1
        regs[46] = (1 << ofs[0]) + ((invert & 1) << ofs[1])
        return regs

    @classmethod
    def regDebug(cls, word1, word2, word3, word4):
        """Returns as numpy arrya of register bytes to set DAC into debug mode"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 2
        regs[1] = 1
        regs[13:17] = littleEndian(word1)
        regs[17:21] = littleEndian(word2)
        regs[21:25] = littleEndian(word3)
        regs[25:29] = littleEndian(word4)
        return regs

    @classmethod
    def regI2C(cls, data, read, ack):
        assert len(data) == len(read) == len(ack), \
            "data, read and ack must have same length for I2C"
        assert len(data) <= 8, "Cannot send more than 8 I2C data bytes"
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0
        regs[1] = 2
        regs[2] = 1 << (8 - len(data))
        regs[3] = sum(((r & 1) << (7 - i)) for i, r in enumerate(read))
        regs[4] = sum(((a & a) << (7 - i)) for i, a in enumerate(ack))
        regs[12:12 - len(data):-1] = data
        return regs

    # Methods to get bytes to write data to the board

    # Direct ethernet server packet creation methods

    def load(self, mem, sram, page=0):
        """Create a packet to write Memory and SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeMemory(mem, p, page=page)
        self.makeSRAM(sram, p, page=page)
        return p

    # Direct ethernet server packet update methods

    @classmethod
    def makeSRAM(cls, data, p, page=0):
        """Update a packet for the ethernet server with SRAM commands.
        
        Build parameters like SRAM_PAGE_LEN are in units of SRAM words,
        each of which is 14+14+4=32 bits = 4 bytes long. Therefore the
        actual length of corresponding byte strings have a *4 multiplier.
        """
        bytesPerDerp = cls.SRAM_WRITE_PKT_LEN * 4
        #Set starting write derp to the beginning of the chosen SRAM page
        writeDerp = page * cls.SRAM_PAGE_LEN / cls.SRAM_WRITE_PKT_LEN
        while len(data) > 0:
            #Chop off enough data for one write packet. This is
            #SRAM_WRITE_PKT_LEN words, which is 4x more bytes.
            #WARNING! string reassignment. Maybe use a pointer instead
            #Note that slicing a np array as myArray[:N], if N is larger
            #than the length of myArray, returns the entirety of myArray
            #and does NOT wrap around to the beginning
            chunk, data = data[:bytesPerDerp], data[bytesPerDerp:]
            chunk = np.fromstring(chunk, dtype='<u4')
            dacPkt = cls.pktWriteSram(writeDerp, chunk)
            p.write(dacPkt.tostring())
            writeDerp += 1

    @classmethod
    def makeMemory(cls, data, p, page=0):
        """Update a packet for the ethernet server with Memory commands."""
        if len(data) > cls.MEM_PAGE_LEN:
            msg = "Memory length %d exceeds maximum length %d (one page)."
            raise Exception(msg % (len(data), cls.MEM_PAGE_LEN))
        # translate SRAM addresses for higher pages
        if page:
            data = cls.shiftSRAM(data, page)
        pkt = cls.pktWriteMem(page, data)
        p.write(pkt.tostring())

    # board communication (can be called from within test mode)
    # Should not be @classmethod because they make board specific direct
    # ethernet server packets.

    def _sendSRAM(self, data):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeSRAM(data, p)
        p.send()

    @inlineCallbacks
    def _runI2C(self, pkts):
        """Run I2C commands on the board."""
        answer = []
        for pkt in pkts:
            while len(pkt):
                data, pkt = pkt[:8], pkt[8:]

                bytes = [(b if b <= 0xFF else 0) for b in data]
                read = [b & self.I2C_RB for b in data]
                ack = [b & self.I2C_ACK for b in data]

                regs = self.regI2C(bytes, read, ack)
                r = yield self._sendRegisters(regs)
                # readout data wrapped around to end
                ansBytes = self.processReadback(r)['I2Cbytes'][-len(data):]

                answer += [b for b, r in zip(ansBytes, read) if r]
        returnValue(answer)

    @inlineCallbacks
    def _runSerial(self, op, data):
        """Run a command or list of commands through the serial interface."""
        answer = []
        for d in data:
            regs = self.regSerial(op, d)
            r = yield self._sendRegisters(regs)
            # turn these into python ints, instead of numpy ints
            answer += [int(self.processReadback(r)['serDAC'])]
        returnValue(answer)

    @inlineCallbacks
    def _setPolarity(self, chan, invert):
        regs = self.regClockPolarity(chan, invert)
        yield self._sendRegisters(regs)
        returnValue(invert)

    @inlineCallbacks
    def _checkPHOF(self, op, fifoReadings, counterValue):
        # Determine for which PHOFs (FIFO offsets) the FIFO counter equals
        # counterValue.
        # Relying on indices matching PHOF values.
        PHOFS = np.where(fifoReadings == counterValue)[0]
        # If no PHOF can be found with the target FIFO counter value...
        if not len(PHOFS):
            PHOF = -1  #Set to -1 so LabRAD call can complete. success=False

        # For each PHOF for which the FIFO counter equals counterValue, resend
        # the PHOF and check that the FIFO counter indeed equals counterValue.
        # If so, return the PHOF and a flag that the FIFO calibration has been
        # successful.
        success = False
        for PHOF in PHOFS:
            pkt = [0x0700 + PHOF, 0x8700]
            reading = long(((yield self._runSerial(op, pkt))[1] >> 4) & 0xF)
            if reading == counterValue:
                success = True
                break
        ans = int(PHOF), success
        returnValue(ans)

    # Externally available board communication methods
    # These run in test mode.
    # Should not be @classmethod

    def initPLL(self):
        """Initial program  of PLL chip
        
        I _believe_ this only has to be run once after the board has been
        powered on. DTS
        """

        @inlineCallbacks
        def func():
            yield self._runSerial(1, [0x1FC093, 0x1FC092, 0x100004, 0x000C11])
            #Run sram with startAddress=endAddress=0. Run once, no loop.
            regs = self.regRunSram(0, 0, loop=False)
            yield self._sendRegisters(regs, readback=False)

        return self.testMode(func)

    def resetPLL(self):
        """Reset PLL"""

        @inlineCallbacks
        def func():
            regs = self.regPllReset()
            yield self._sendRegisters(regs)

        return self.testMode(func)

    def debugOutput(self, word1, word2, word3, word4):
        @inlineCallbacks
        def func():
            pkt = self.regDebug(word1, word2, word3, word4)
            yield self._sendRegisters(pkt)

        return self.testMode(func)

    def runSram(self, dataIn, loop, blockDelay):
        @inlineCallbacks
        def func():
            pkt = self.regPing()
            yield self._sendRegisters(pkt)

            data = np.array(dataIn, dtype='<u4').tostring()
            yield self._sendSRAM(data)
            startAddr, endAddr = 0, len(data) / 4

            pkt = self.regRunSram(startAddr, endAddr, loop, blockDelay)
            yield self._sendRegisters(pkt, readback=False)

        return self.testMode(func)

    def runI2C(self, pkts):
        """Run I2C commands on the board."""
        return self.testMode(self._runI2C, pkts)

    def runSerial(self, op, data):
        """Run a command or list of commands through the serial interface."""
        return self.testMode(self._runSerial, op, data)

    def setPolarity(self, chan, invert):
        """Sets the clock polarity for either DAC. (DAC only)"""
        return self.testMode(self._setPolarity, chan, invert)

    def setLVDS(self, cmd, sd, optimizeSD):
        """
        INPUTS
        cmd - int: 2 for DAC A, 3 for DAC B
        sd - :
        optimizeSD - bool:
        
        Returns (success, MSD, MHD, t, (range(16), MSDbits, MHDbits), checkHex)
        success - bool: 
        MSD - int:
        MHD - int:
        t - :
        range(16)
        MSDbits - :
        MHDbits - :
        checkHes - :
        """

        @inlineCallbacks
        # See U:\John\ProtelDesigns\GHzDAC_R3_1\Documentation\HardRegProgram.txt
        # for how this function works.
        def func():
            #TODO: repeat LVDS measurement five times and average results.
            pkt = [[0x0400 + (i << 4), 0x8500, 0x0400 + i, 0x8500][j]
                   for i in range(16) for j in range(4)]

            if optimizeSD is True:
                # Find the leading/trailing edges of the DATACLK_IN clock.
                # First set SD to 0. Then, for bits from 0 to 15, set MSD to
                # this bit and MHD to 0, read the check bit, set MHD to this
                # bit and MSD to 0, read the check bit.
                answer = yield self._runSerial(cmd, [0x0500] + pkt)
                answer = [answer[i * 2 + 2] & 1 for i in range(32)]

                # Find where check bit changes from 1 to 0 for MSD and MHD.
                MSD = -2
                MHD = -2
                for i in range(16):
                    if MSD == -2 and answer[i * 2] == 1: MSD = -1
                    if MSD == -1 and answer[i * 2] == 0: MSD = i
                    if MHD == -2 and answer[i * 2 + 1] == 1: MHD = -1
                    if MHD == -1 and answer[i * 2 + 1] == 0: MHD = i
                MSD = max(MSD, 0)
                MHD = max(MHD, 0)
                # Find the optimal SD based on MSD and MHD.
                t = (MHD - MSD) / 2 & 0xF
                setMSDMHD = False
            elif sd is None:
                # Get the SD value from the registry.
                t = int(self.boardParams['lvdsSD']) & 0xF
                MSD, MHD = -1, -1
                setMSDMHD = True
            else:
                # This occurs if the SD is not specified (by optimization or
                # in the registry).
                t = sd & 0xF
                MSD, MHD = -1, -1
                setMSDMHD = True

            # Set the SD and check that the resulting difference between MSD
            # and MHD is no more than one bit. Any more indicates noise on the
            # line.
            answer = yield self._runSerial(cmd, [0x0500 + (t << 4)] + pkt)
            MSDbits = [bool(answer[i * 4 + 2] & 1) for i in range(16)]
            MHDbits = [bool(answer[i * 4 + 4] & 1) for i in range(16)]
            MSDswitch = [(MSDbits[i + 1] != MSDbits[i]) for i in range(15)]
            MHDswitch = [(MHDbits[i + 1] != MHDbits[i]) for i in range(15)]
            #Find first index at which MHD/MSD switch
            leadingEdge = MSDswitch.index(True)
            trailingEdge = MHDswitch.index(True)
            if setMSDMHD:
                if sum(MSDswitch) == 1: MSD = leadingEdge
                if sum(MHDswitch) == 1: MHD = trailingEdge
            if abs(trailingEdge - leadingEdge) <= 1 and sum(MSDswitch) == 1 and \
                            sum(MHDswitch) == 1:
                success = True
            else:
                success = False
            checkResp = yield self._runSerial(cmd, [0x8500])
            checkHex = checkResp[0] & 0x7
            returnValue((success, MSD, MHD, t, (range(16), MSDbits, MHDbits),
                         checkHex))

        return self.testMode(func)

    def setFIFO(self, chan, op, targetFifo):
        if targetFifo is None:
            # Grab targetFifo from registry if not specified.
            targetFifo = int(self.boardParams['fifoCounter'])

        @inlineCallbacks
        def func():
            # set clock polarity to positive
            clkinv = False
            yield self._setPolarity(chan, clkinv)

            tries = 1
            found = False

            while tries <= self.MAX_FIFO_TRIES and not found:
                # Send all four PHOFs & measure resulting FIFO counters. If
                # one of these equals targetFifo, set the PHOF and check that
                # the FIFO counter is indeed targetFifo. If so, break out.
                pkt = [0x0700, 0x8700, 0x0701, 0x8700, 0x0702, 0x8700,
                       0x0703, 0x8700]
                reading = yield self._runSerial(op, pkt)
                fifoCounters = np.array([(reading[i] >> 4) & 0xF for i in \
                                         [1, 3, 5, 7]])
                PHOF, found = yield self._checkPHOF(op, fifoCounters,
                                                    targetFifo)
                if found:
                    break
                else:
                    # If none of PHOFs gives FIFO counter of targetFifo
                    # initially or after verification, flip clock polarity and
                    # try again.
                    clkinv = not clkinv
                    yield self._setPolarity(chan, clkinv)
                    tries += 1

            ans = found, clkinv, PHOF, tries, targetFifo
            returnValue(ans)

        return self.testMode(func)

    def runBIST(self, cmd, shift, dataIn):
        """

        :param cmd: 2 or 3
        :param shift: 0 or 14, i.e. whether to use DAC A or B
        :param dataIn: SRAM data to use with BIST (random)
        :return:
        """

        @inlineCallbacks
        def func():
            pkt = self.regRunSram(0, 0, loop=False)
            yield self._sendRegisters(pkt, readback=False)

            dat = [d & 0x3FFF for d in dataIn]
            data = [0, 0, 0, 0] + [d << shift for d in dat]
            # make sure data is at least 20 words long by appending 0's
            data += [0] * (20 - len(data))
            data = np.array(data, dtype='<u4').tostring()
            yield self._sendSRAM(data)
            startAddr, endAddr = 0, len(data) // 4
            yield self._runSerial(cmd, [0x0004, 0x1107, 0x1106])

            pkt = self.regRunSram(startAddr, endAddr, loop=False)
            yield self._sendRegisters(pkt, readback=False)

            seq = [0x1126, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x1166, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11A6, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11E6, 0x9200, 0x9300, 0x9400, 0x9500]
            theory = tuple(self.bistChecksum(dat))
            bist = yield self._runSerial(cmd, seq)
            reading = [(bist[i + 4] << 0) + (bist[i + 3] << 8) +
                       (bist[i + 2] << 16) + (bist[i + 1] << 24)
                       for i in [0, 5, 10, 15]]
            lvds, fifo = tuple(reading[0:2]), tuple(reading[2:4])

            print "bist = ", bist
            print "reading = ", reading

            # lvds and fifo may be reversed.  This is okay
            lvds = lvds[::-1] if lvds[::-1] == theory else lvds
            fifo = fifo[::-1] if fifo[::-1] == theory else fifo
            returnValue((lvds == theory and fifo == theory, theory, lvds,
                         fifo))

        return self.testMode(func)

    # Utility

    @staticmethod
    def processReadback(resp):
        """Interpret byte string returned by register readback"""
        a = np.fromstring(resp, dtype='<u1')
        return {
            'build': a[51],
            'serDAC': a[56],
            'noPllLatch': bool((a[58] & 0x80) > 0),
            'ackoutI2C': a[61],
            'I2Cbytes': a[69:61:-1],
            'executionCounter': (a[53] << 8) + a[52]
        }


fpga.REGISTRY[('DAC', 7)] = DAC_Build7


class DacRunner_Build8(DacRunner_Build7):
    pass


class DAC_Build8(DAC_Build7):
    RUNNER_CLASS = DacRunner_Build8

    SRAM_LEN = 18432
    SRAM_WRITE_PKT_LEN = 256
    SRAM_WRITE_DERPS = SRAM_LEN // SRAM_WRITE_PKT_LEN
    SRAM_PAGE_LEN = 9216
    SRAM_DELAY_LEN = 1024
    SRAM_BLOCK0_LEN = 16384
    SRAM_BLOCK1_LEN = 2048


fpga.REGISTRY[('DAC', 8)] = DAC_Build8

### classes below this line are NOT properly implemented!!!


class DacRunner_Build11(DacRunner_Build7):
    pass


class DAC_Build11(DAC_Build7):
    RUNNER_CLASS = DacRunner_Build11


fpga.REGISTRY[('DAC', 11)] = DAC_Build11


### Jump table

class DacRunner_Build13(DacRunner_Build7):
    # noinspection PyMissingConstructor
    def __init__(self, dev, reps, start_delay, jt_entries, jt_counters, sram):
        """

        :type dev: DAC_Build13
        :param reps:
        :param start_delay:
        :param jt_entries:
        :param jt_counters:
        :param sram:
        :return:
        """
        self.dev = dev
        self.reps = reps
        self.start_delay = start_delay
        self.jump_table = jumpTable.JumpTable(jumps=jt_entries, counters=jt_counters)  # TODO: start address?
        self.sram = sram
        self.nPackets = 0  # we don't expect any packets back

    def pageable(self):
        return False  # no paging for JT

    def loadPacket(self, page, isMaster):
        """Create pipelined load packet.  For DAC, upload mem and SRAM."""
        if isMaster:
            # TODO: how can we add a delay to the JT?
            self.start_delay += MASTER_SRAM_DELAY
        return self.dev.load(self.jump_table, self.sram)

    def runPacket(self, page, slave, delay, sync):
        """Create run packet."""
        startDelay = self.startDelay + delay
        regs = self.dev.regRun(self.reps, page, slave, startDelay,
                               blockDelay=None, sync=sync)
        return regs


class DAC_Build13(DAC_Build7):
    RUNNER_CLASS = DacRunner_Build13
    JUMP_TABLE_LEN = 528
    NUM_COUNTERS = 4

    def buildRunner(self, reps, info):
        """
        :param reps:
        :param info:
        :return:
        """
        jt_entries = info['jt_entries']
        jt_counters = info['jt_counters']
        start_delay = info.get('startDelay', 0)
        sram = info.get('sram', None)
        runner = self.RUNNER_CLASS(self, reps, start_delay, jt_entries, jt_counters, sram)
        return runner

    # let's check the various registry functions.
    # OK means old implementation should work

    # regPing -- OK
    # regPllQuery -- ?OK?
    # regSerial -- OK
    # regPllReset -- OK
    # resetPll -- OK

    @classmethod
    def regRun(cls, reps, page, slave, delay, blockDelay=None, sync=0):
        # TODO: probably get rid of page, blockDelay
        if blockDelay is not None:
            raise ValueError("JT board got a non-None blockDelay: ", blockDelay)
        if page:
            raise ValueError("JT board got a non-zero page: ", page)
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        # old version of slave: 0 = master, 1 = slave, 3 = idle (bit 43)
        # new version: 0 = idle, 1 = master, 2 = test, 3 = slave (bit 0)
        if slave == 0:
            start = 1
        elif slave == 1:
            start = 3
        elif slave == 3:
            start = 0
        else:
            raise ValueError('"slave" must be 0, 1, or 3, not %s' % slave)
        regs[0] = start
        regs[1] = 0  # TODO: what kind of readback do we want?
        regs[13:15] = littleEndian(reps, 2)
        regs[43:45] = littleEndian(int(delay), 2)
        regs[45] = sync
        regs[17] = 0  # Which jump table to count activations of
        regs[51] = 2  # Monitor 0
        regs[52] = 2  # Monitor 1

        return regs

    @classmethod
    def regRunSimple(cls):
        """
        just run the thing
        :return: register packet data
        """
        return cls.regRun(1, 0, 0, 0)

    @classmethod
    def regRunSram(cls, startAddr, endAddr, loop=True, blockDelay=0, sync=249):
        raise NotImplementedError("register run SRAM not valid for jump table DACs")

    @classmethod
    def regIdle(cls, delay):
        """
        :param delay: start delay
        :return: numpy array of register bytes for idle mode
        :rtype: numpy.ndarray
        """
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0  # do not start, daisy pass-through
        regs[1] = 0  # no readback
        regs[43:45] = littleEndian(int(delay), 2)
        return regs

    @classmethod
    def regDebug(cls, word1, word2, word3, word4):
        raise NotImplementedError("Not sure what debug means for the JT")

    # regClockPolarity -- OK
    # regDebug -- OK
    # regI2C -- OK
    # makeSram -- OK

    def load(self, jt, sram, page=None):
        if page is not None:
            raise NotImplementedError("page argument not valid for jump table")
        p = self.makePacket()
        self.makeJumpTable(jt, p)
        self.makeSRAM(sram, p)
        return p

    @classmethod
    def makeJumpTable(cls, jtObj, p):
        """
        TODO: do we even need this function?
        :param jumpTable.JumpTable jtObj: jump table object
        :param p: packet to be added to
        :return: None
        """
        p.write(jtObj.toString())

    @classmethod
    def makeMemory(cls, data, p, page=0):
        raise NotImplementedError("No memory commands for jump table!")

    @classmethod
    def pktWriteMem(cls, page, data):
        raise NotImplementedError("No memory commands for jump table!")

    def initPLL(self):
        @inlineCallbacks
        def func():
            yield self._runSerial(1, [0x1FC093, 0x1FC092, 0x100004, 0x000C11])
            jt = jumpTable.jtRunSram(0, 0, False)
            yield self._sendJumpTable(jt)
            yield self._sendRegisters(self.regRunSimple())

        return self.testMode(func)

    def runSram(self, dataIn, loop, blockDelay):
        @inlineCallbacks
        def func():
            yield self._sendRegisters(self.regPing())  # Why is this here? DTS/PJJO
            data = np.array(dataIn, dtype='<u4').tostring()
            yield self._sendSRAM(data)
            startAddr, endAddr = 0, len(data) // 4
            jt = jumpTable.jtRunSram(startAddr, endAddr, loop)
            yield self._sendJumpTable(jt)
            yield self._sendRegisters(self.regRunSimple(), readback=False)

        return self.testMode(func)

    def runBIST(self, cmd, shift, dataIn):
        """ Run a BIST on given SRAM sequence. Jump Table DAC version.
        This is rewritten from the non-JT version because we can no longer
        run the SRAM directly with a register write.
        :param cmd: serial operation to run.
        :param shift: bit shift SRAM data by this amount (e.g. 14 for DAC B)
        :param dataIn: input SRAM data
        :return: (bool--checksums match?, checksum, lvds, fifo)
        """

        @inlineCallbacks
        def func():
            # do nothing run
            jt = jumpTable.jtRunSram(0, 0, loop=False)
            yield self._sendJumpTable(jt)
            yield self._sendRegisters(self.regRunSimple(), readback=False)

            # serial run?
            dat = [d & 0x3FFF for d in dataIn]
            data = [0, 0, 0, 0] + [d << shift for d in dat]
            # make sure data is at least 20 words long by appending 0's
            data += [0] * (20 - len(data))
            data = np.array(data, dtype='<u4').tostring()
            yield self._sendSRAM(data)
            yield self._runSerial(cmd, [0x0004, 0x1107, 0x1106])

            # JT run
            startAddr, endAddr = 0, len(data) // 4
            jt = jumpTable.jtRunSram(startAddr, endAddr, loop=False)
            yield self._sendJumpTable(jt)
            yield self._sendRegisters(self.regRunSimple(), readback=False)

            # checksum
            seq = [0x1126, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x1166, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11A6, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11E6, 0x9200, 0x9300, 0x9400, 0x9500]
            theory = tuple(self.bistChecksum(dat))
            bist = yield self._runSerial(cmd, seq)
            reading = [(bist[i + 4] << 0) + (bist[i + 3] << 8) +
                       (bist[i + 2] << 16) + (bist[i + 1] << 24)
                       for i in [0, 5, 10, 15]]
            print "bist = ", bist
            print "reading = ", reading
            lvds, fifo = tuple(reading[0:2]), tuple(reading[2:4])

            # lvds and fifo may be reversed.  This is okay
            lvds = lvds[::-1] if lvds[::-1] == theory else lvds
            fifo = fifo[::-1] if fifo[::-1] == theory else fifo
            returnValue((lvds == theory and fifo == theory, theory, lvds, fifo))
        return self.testMode(func)

    # extensions to board communication
    def _sendJumpTable(self, jtObj):
        """Write jump table data to the FPGA."""
        p = self.makePacket()
        self.makeJumpTable(jtObj, p)
        p.send()



fpga.REGISTRY[('DAC', 13)] = DAC_Build13

#Utility functions

def maxSRAM(cmds):
    """Determines the maximum SRAM address used in a memory sequence.

    This is used to determine whether a given memory sequence is pageable,
    since only half of the available SRAM can be used when paging.
    """

    def addr(cmd):
        return MemorySequence.getAddress(cmd) if \
            MemorySequence.getOpcode(cmd) in [0x8, 0xA] else 0

    return max(addr(cmd) for cmd in cmds)


#Memory sequence functions

class MemorySequence(list):
    @staticmethod
    def getOpcode(cmd):
        return (cmd & 0xF00000) >> 20

    @staticmethod
    def getAddress(cmd):
        return (cmd & 0x0FFFFF)

    def noOp(self):
        self.append(0x000000)
        return self

    def delayCycles(self, cycles):
        assert cycles <= 0xfffff
        cmd = 0x300000
        cycles = int(cycles) & 0xfffff
        self.append(cmd + cycles)
        return self

    def fo(self, ch, data):
        cmd = {0: 0x100000, 1: 0x200000}[ch]
        cmd = cmd + (int(data) & 0xfffff)
        self.append(cmd)
        return self

    def fastbias(self, fo, fbDac, data, slow):
        """Set a fastbias DAC
        
        fo - int: Which fiber to use on GHzDAC. Either 0 or 1
        fbDac - int: Which fastbias DAC. Either 0 or 1
        data: DAC level
        slow: Slow or fast channel. 1 = slow, 0 = fast.
            Only relevant for coarse DAC>
        
        NOTES:
        fbDac slow  channel
        0     0     FINE
        0     1     N/A (ignored?)
        1     0     COARSE FAST
        1     1     COARSE SLOW
        """
        if fbDac not in [0, 1]:
            raise RuntimeError('fbDac must be 0 or 1')
        if slow not in [0, 1]:
            raise RuntimeError('slow must be 0 or 1')
        a = {0: 0x100000, 1: 0x200000}[fo]
        b = (data & 0xffff) << 3
        c = fbDac << 19
        d = slow << 2
        self.append(a + b + c + d)
        return self

    def sramStartAddress(self, addr):
        self.append(0x800000 + addr)
        return self

    def sramEndAddress(self, addr):
        self.append(0xA00000 + addr)
        return self

    def runSram(self):
        self.append(0xC00000)
        return self

    def startTimer(self):
        self.append(0x400000)
        return self

    def stopTimer(self):
        self.append(0x400001)
        return self

    def branchToStart(self):
        self.append(0xf00000)
        return self

    @staticmethod
    def addMasterDelay(cmds, delay_us=MASTER_SRAM_DELAY):
        """Add delays to master board before SRAM calls.
        
        Creates a memory sequence with delays added before all SRAM
        calls to ensure that boards stay properly synchronized by
        allowing extra time for slave boards to reach the SRAM
        synchronization point.  The delay is specified in microseconds.
        
        TODO: check for repeated delay calls to make sure delays actually happen
        """
        newCmds = []
        delayCycles = int(delay_us * 25)  #memory clock speed is 25MHz
        assert delayCycles < 0xFFFFF
        delayCmd = 0x300000 + delayCycles
        for cmd in cmds:
            if MemorySequence.getOpcode(cmd) == 0xC:  # call SRAM
                newCmds.append(delayCmd)  # add delay
            newCmds.append(cmd)
        return newCmds

    @staticmethod
    def cmdTime_cycles(cmd):
        """A conservative estimate of the number of cycles a given command takes.
        
        SRAM calls are assumed to take 12us. This is an upper bound.
        """
        opcode = MemorySequence.getOpcode(cmd)
        # noOp, fiber 0 out, fiber 1 out, start/stop timer, sram start addr,
        # sram end addr
        if opcode in [0x0, 0x1, 0x2, 0x4, 0x8, 0xA]:
            return 1
        #branch to start
        if opcode == 0xF:
            return 2
        #delay
        if opcode == 0x3:
            return MemorySequence.getAddress(cmd) + 1
        #run sram
        if opcode == 0xC:
            # TODO: Incorporate SRAMoffset when calculating sequence time.
            #       This gives a max of up to 12 + 255 us
            return 25 * 12  # maximum SRAM length is 12us, with 25 cycles per us

    @staticmethod
    def sequenceTime_sec(cmds):
        """Conservative estimate of the length of a sequence in seconds.
        
        cmds - list of numbers: memory commands for GHz DAC
        """
        cycles = sum(MemorySequence.cmdTime_cycles(c) for c in cmds)
        return cycles * 40e-9  # assume 25 MHz clock -> 40 ns per cycle

    @staticmethod
    def fixSRAMaddresses(mem, sram, device):
        """Set the addresses of SRAM calls for multiblock sequences.
        
        The addresses are set according to the following diagrams:
        
        FIG1
        row1    00000000000000-------||-----00000
        row2    ^             x     ^||^   x    ^
        
        FIG2
        row1    00000000000000-------|             |-----00000
        row2    ^             x     ^|    DELAY    |^   x    ^
        
        FIG1 shows the physical sram block whereas FIG2 shows the sram as
        seen by the GHz clock, eg. including the inter-block delay.
        
        row1 represents the sram data:
            0's indicate unused SRAM words
            -'s indicate used SRAM words
        row2 shows important points:
            ^'s indicate the physical start and end points of the SRAM blocks
            x's indicate where we want the sram to start and stop execution
        
        Note that in FIG2 the distance between the starting x and the final x
        is larger than in FIG1. This means that the final SRAM word occurs at
        a clock count DELAY later than you would expect given the its
        _physical_ location in the memory block. This clock count is what
        matters, so when we write the end address we have to include DELAY,
        Block0 length + length of signal in block1 + DELAY = endAddr,
        in other words, endAddr is equal to
        # of 0s in block0 + # of -'s in block0 + # of -'s in block1 + DELAY
        """
        block0Len_words = len(sram[0]) / 4
        block1Len_words = len(sram[1]) / 4
        delayBlocks = sram[2]
        if not isinstance(sram, tuple):
            return mem
        numSramCalls = sum(MemorySequence.getOpcode(cmd) == 0xC for cmd in mem)
        if numSramCalls > 1:
            raise Exception('Only one SRAM call allowed in multi-block sequences.')

        def fixAddr(cmd):
            opcode, address = MemorySequence.getOpcode(cmd), MemorySequence.getAddress(cmd)
            if opcode == 0x8:
                # SRAM start address
                address = device.SRAM_BLOCK0_LEN - block0Len_words
                return (opcode << 20) + address
            elif opcode == 0xA:
                # SRAM end address
                address = device.SRAM_BLOCK0_LEN + block1Len_words \
                          + device.SRAM_DELAY_LEN * delayBlocks - 1
                return (opcode << 20) + address
            else:
                return cmd

        return [fixAddr(cmd) for cmd in mem]

    @staticmethod
    def timerCount(cmds):
        """Return the number of timer stops in a memory sequence.

        This should correspond to the number of timing results per
        repetition of the sequence.  Note that this method does no
        checking of the timer logic, for example whether every stop
        has a corresponding start.  That sort of checking is the
        user's responsibility at this point (if using the qubit server,
        these things are automatically checked).
        """
        return int(sum(np.asarray(cmds) == 0x400001))  # numpy version
        #return cmds.count(0x400001) # python list version
