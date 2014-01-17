import numpy as np

import fpga

# named functions
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock


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
#   SRAM_LEN - The length, in SRAM words, of the total SRAM memory
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

class DAC_B7(fpga.DAC):
    """Manages communication with a single GHz DAC board.

    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    MEM_LEN = 512
    MEM_PAGE_LEN = 256
    TIMING_PACKET_LEN = 30
    # timing estimates are multiplied by this factor to determine sequence
    # timeout
    TIMEOUT_FACTOR = 10
    I2C_RB = 0x100
    I2C_ACK = 0x200
    I2C_RB_ACK = I2C_RB | I2C_ACK
    I2C_END = 0x400
    MAX_FIFO_TRIES = 5
    
    # Methods to get bytes to be written to register
    
    @classmethod
    def regRun(cls, reps, page, slave, delay, blockDelay=None, sync=249):
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1 + (page << 7) # run memory in specified page
        regs[1] = 3 # stream timing data
        regs[13:15] = littleEndian(reps, 2)
        if blockDelay is not None:
            regs[19] = blockDelay # for boards running multi-block sequences
        regs[43] = int(slave)
        # Addressing out of order because we added the high byte for start
        # delay after the rest of the registers had been defined.
        regs[44],regs[51] = littleEndian(int(delay),2)
        regs[45] = sync
        return regs
    
    @classmethod
    def regRunSram(cls, startAddr, endAddr, loop=True, blockDelay=0, sync=249):
        regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
        regs[0] = (3 if loop else 4) #3: continuous, 4: single run
        regs[1] = 0 #No register readback
        regs[13:16] = littleEndian(startAddr, 3) #SRAM start address
        regs[16:19] = littleEndian(endAddr-1 + cls.SRAM_DELAY_LEN \
            * blockDelay, 3) #SRAM end
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
        regs[0] = 0 # do not start
        regs[1] = 0 # no readback
        regs[43] = 3 # IDLE mode
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
        regs[12:12-len(data):-1] = data
        return regs
    
    # Methods to get bytes to write data to the board
    
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
        assert 0< len(data) <= cls.SRAM_WRITE_PKT_LEN, \
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
        
        pkt[2:2+len(data)*4:4] = (data >> 0) & 0xFF #Least sig. byte
        pkt[3:3+len(data)*4:4] = (data >> 8) & 0xFF
        pkt[4:4+len(data)*4:4] = (data >> 16) & 0xFF
        pkt[5:5+len(data)*4:4] = (data >> 24) & 0xFF #Most sig. byte
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
        pkt[1:1+len(data)*3:3] = (data >> 0) & 0xFF
        pkt[2:2+len(data)*3:3] = (data >> 8) & 0xFF
        pkt[3:3+len(data)*3:3] = (data >> 16) & 0xFF
        #a, b, c = littleEndian(data, 3)
        #pkt[1:1+len(data)*3:3] = a
        #pkt[2:2+len(data)*3:3] = b
        #pkt[3:3+len(data)*3:3] = c
        return pkt
    
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
            'executionCounter': (a[53]<<8) + a[52]
        }
    
    
    # lifecycle methods
    
    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """Establish a connection to the board."""
        print('connecting to DAC board: %s (build #%d)'% \
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
        p.cd(['','Servers','GHz FPGAs'])
        p.get('dac'+self.devName.split(' ')[-1], key='boardParams')
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
            #than the length of myArray, returns the entirty of myArray
            #and does NOT wrap around to the beginning
            chunk, data = data[:bytesPerDerp], data[bytesPerDerp:]
            chunk = np.fromstring(chunk, dtype='<u4')
            dacPkt = self.pktWriteSram(writeDerp, chunk)
            p.write(dacPkt.tostring())
            writeDerp += 1
    
    @classmethod
    def makeMemory(cls, data, p, page=0):
        """Update a packet for the ethernet server with Memory commands."""
        if len(data) > MEM_PAGE_LEN:
            msg = "Memory length %d exceeds maximum length %d (one page)."
            raise Exception(msg % (len(data), MEM_PAGE_LEN))
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
                read = [b & I2C_RB for b in data]
                ack = [b & I2C_ACK for b in data]
                
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
            regs = regSerial(op, d)
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
            PHOF = -1 #Set to -1 so LabRAD call can complete. success=False
        
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
            regs = regPllReset()
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
            pkt = regPing()
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
            pkt = [[0x0400 + (i<<4), 0x8500, 0x0400 + i, 0x8500][j]
                   for i in range(16) for j in range(4)]
    
            if optimizeSD is True:
                # Find the leading/trailing edges of the DATACLK_IN clock.
                # First set SD to 0. Then, for bits from 0 to 15, set MSD to
                # this bit and MHD to 0, read the check bit, set MHD to this
                # bit and MSD to 0, read the check bit.
                answer = yield self._runSerial(cmd, [0x0500] + pkt)
                answer = [answer[i*2+2] & 1 for i in range(32)]
    
                # Find where check bit changes from 1 to 0 for MSD and MHD.
                MSD = -2
                MHD = -2
                for i in range(16):
                    if MSD == -2 and answer[i*2] == 1: MSD = -1
                    if MSD == -1 and answer[i*2] == 0: MSD = i
                    if MHD == -2 and answer[i*2+1] == 1: MHD = -1
                    if MHD == -1 and answer[i*2+1] == 0: MHD = i
                MSD = max(MSD, 0)
                MHD = max(MHD, 0)
                # Find the optimal SD based on MSD and MHD.
                t = (MHD-MSD)/2 & 0xF
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
            answer = yield self._runSerial(cmd, [0x0500 + (t<<4)] + pkt)
            MSDbits = [bool(answer[i*4+2] & 1) for i in range(16)]
            MHDbits = [bool(answer[i*4+4] & 1) for i in range(16)]
            MSDswitch = [(MSDbits[i+1] != MSDbits[i]) for i in range(15)]
            MHDswitch = [(MHDbits[i+1] != MHDbits[i]) for i in range(15)]
            #Find first index at which MHD/MSD switch
            leadingEdge = MSDswitch.index(True)
            trailingEdge = MHDswitch.index(True)
            if setMSDMHD:
                if sum(MSDswitch)==1: MSD = leadingEdge
                if sum(MHDswitch)==1: MHD = trailingEdge
            if abs(trailingEdge-leadingEdge)<=1 and sum(MSDswitch)==1 and \
              sum(MHDswitch)==1:
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
    
            while tries <= MAX_FIFO_TRIES and not found:
                # Send all four PHOFs & measure resulting FIFO counters. If
                # one of these equals targetFifo, set the PHOF and check that
                # the FIFO counter is indeed targetFifo. If so, break out.
                pkt =  [0x0700, 0x8700, 0x0701, 0x8700, 0x0702, 0x8700,
                        0x0703, 0x8700]
                reading = yield self._runSerial(op, pkt)
                fifoCounters = np.array([(reading[i]>>4) & 0xF for i in \
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
        """Run a BIST on the given SRAM sequence. (DAC only)"""
        @inlineCallbacks
        def func():
            pkt = self.regRunSram(0, 0, loop=False)
            yield self._sendRegisters(pkt, readback=False)
    
            dat = [d & 0x3FFF for d in dataIn]
            data = [0, 0, 0, 0] + [d << shift for d in dat]
            # make sure data is at least 20 words long by appending 0's
            data += [0] * (20-len(data))
            data = np.array(data, dtype='<u4').tostring()
            yield self._sendSRAM(data)
            startAddr, endAddr = 0, len(data) / 4
            yield self._runSerial(cmd, [0x0004, 0x1107, 0x1106])
    
            pkt = self.regRunSram(startAddr, endAddr, loop=False)
            yield self._sendRegisters(pkt, readback=False)
    
            seq = [0x1126, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x1166, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11A6, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11E6, 0x9200, 0x9300, 0x9400, 0x9500]
            theory = tuple(self.bistChecksum(dat))
            bist = yield self._runSerial(cmd, seq)
            reading = [(bist[i+4] <<  0) + (bist[i+3] <<  8) +
                       (bist[i+2] << 16) + (bist[i+1] << 24)
                       for i in [0, 5, 10, 15]]
            lvds, fifo = tuple(reading[0:2]), tuple(reading[2:4])
    
            # lvds and fifo may be reversed.  This is okay
            lvds = lvds[::-1] if lvds[::-1] == theory else lvds
            fifo = fifo[::-1] if fifo[::-1] == theory else fifo
            returnValue((lvds == theory and fifo == theory, theory, lvds,
                         fifo))
        return self.testMode(func)

fpga.REGISTRY[('DAC', 7)] = DAC_B7

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
        self.append(cmd+cycles)
        return self
    
    def fo(self, ch, data):
        cmd = {0:0x100000, 1:0x200000}[ch]
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
        if fbDac not in [0,1]:
            raise RuntimeError('fbDac must be 0 or 1')
        if slow not in [0,1]:
            raise RuntimeError('slow must be 0 or 1')
        a = {0:0x100000,1:0x200000}[fo]
        b = (data & 0xffff) << 3
        c = fbDac << 19
        d = slow << 2
        self.append(a+b+c+d)
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

