import numpy as np

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock

REG_PACKET_LEN = 56

READBACK_LEN = 70

#SRAM definitions
#The word "page" used to be overloaded. An SRAM "page" referred to a chunk of 256 SRAM
#words written by one ethernet packet.
#In the FPGA server coding we use "page" to refer to a section of the physical SRAM used
#in a sequence, where we have two pages to allow for simultaneous execution and
#download of next sequence.
#To clarify this we now call a group of 256 SRAM words written by an ethernet packet a "derp"
#block0 = normal SRAM. 32 derps
#block1 = used for extended sequences. 8 derps
#Total number of packets = 40 -> 40 derps * 256 words per derp = 10240 words

MASTER_SRAM_DELAY = 2 # microseconds for master to delay before SRAM to ensure synchronization

MEM_LEN = 512
MEM_PAGE_LEN = 256

TIMING_PACKET_LEN = 30

TIMEOUT_FACTOR = 10 # timing estimates are multiplied by this factor to determine sequence timeout

I2C_RB = 0x100
I2C_ACK = 0x200
I2C_RB_ACK = I2C_RB | I2C_ACK
I2C_END = 0x400


def macFor(board):
    """Get the MAC address of a DAC board as a string."""
    return '00:01:CA:AA:00:' + ('0'+hex(int(board))[2:])[-2:].upper()

def isMac(mac):
    return mac.startswith('00:01:CA:AA:00:')


# functions to register packets for DAC boards

def regPing():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0 #No sequence start
    regs[1] = 1 #Readback after 2us
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
    regs[0] = (3 if loop else 4) #3: continuous, 4: single run
    regs[1] = 0 #No register readback
    regs[13:16] = littleEndian(startAddr, 3) #SRAM start address
    regs[16:19] = littleEndian(endAddr-1 + self.SRAM_DELAY_LEN * blockDelay, 3) #SRAM end
    regs[19] = blockDelay
    regs[45] = sync
    return regs

def regClockPolarity(chan, invert):
    ofs = {'A': (4, 0), 'B': (5, 1)}[chan]
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 1
    regs[46] = (1 << ofs[0]) + ((invert & 1) << ofs[1])
    return regs

def regPllReset():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0
    regs[1] = 1
    regs[46] = 0x80 #Set d[7..0] to 10000000 = reset 1GHz PLL pulse
    return regs

def regPllQuery():
    return regPing()

def regSerial(op, data):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 0 #Start mode = no start
    regs[1] = 1 #Readback = readback after 2us to allow for serial
    regs[47] = op #Set serial operation mode to op
    regs[48:51] = littleEndian(data, 3) #Serial data
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

def regRun(reps, page, slave, delay, blockDelay=None, sync=249):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1 + (page << 7) # run memory in specified page
    regs[1] = 3 # stream timing data
    regs[13:15] = littleEndian(reps, 2)
    if blockDelay is not None:
        regs[19] = blockDelay # for boards running multi-block sequences
    regs[43] = int(slave)
    regs[44],regs[51] = littleEndian(int(delay),2) #this is weird because we added the high byte for start delay after the rest of the registers had been defined.
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
        'noPllLatch': bool((a[58] & 0x80) > 0),
        'ackoutI2C': a[61],
        'I2Cbytes': a[69:61:-1],
    }

def pktWriteSram(derp, data):
    assert 0 <= derp < SRAM_WRITE_DERPS, "SRAM derp out of range: %d" % derp 
    data = np.asarray(data)
    pkt = np.zeros(1026, dtype='<u1')
    pkt[0] = (derp >> 0) & 0xFF
    pkt[1] = (derp >> 8) & 0xFF
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



class DacDevice(DeviceWrapper):
    """Manages communication with a single GHz DAC board.

    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    # lifecycle functions for this device wrapper
    
    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """Establish a connection to the board."""
        print 'connecting to DAC board: %s (build #%d)' % (macFor(board), build)

        self.boardGroup = group
        self.server = de
        self.cxn = de._cxn
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = macFor(board)
        self.devName = name
        self.serverName = de._labrad_name
        self.timeout = T.Value(1, 's')

        # set up our context with the ethernet server
        # This context is expired when the device shuts down
        p = self.makePacket()
        p.connect(port)
        p.require_length(READBACK_LEN)
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()
        
        #Get build specific information about this device
        reg = self.cxn.registry
        ctxt = reg.context()
        p = reg.packet()
        p.cd(['','Servers','GHz FPGAs'])
        p.get('build'+str(self.build))
        hardwareParams = yield p.send()
        print self.devName+' hardware params: '+str(hardwareParams)
        self.parseHardwareParameters(hardwareParams)
        yield self.cxn.manager.expire_context(reg.ID, context=ctxt)

    @inlineCallbacks
    def shutdown(self):
        """Called when this device is to be shutdown."""
        yield self.cxn.manager.expire_context(self.server.ID, context=self.ctx)


    # packet creation functions

    def makePacket(self):
        """Create a new packet to be sent to the ethernet server for this device."""
        return self.server.packet(context=self.ctx)

    def makeSRAM(self, data, p, page=0):
        """Update a packet for the ethernet server with SRAM commands."""
        #Set starting write derp to the beginning of the chosen SRAM page
        writeDerp = page * self.SRAM_PAGE_LEN / self.SRAM_WRITE_PKT_LEN
        #Crete SRAM write commands and add them to the packet for the direct ethernet server
        while len(data) > 0:
            chunk, data = data[:self.SRAM_WRITE_PKT_LEN*4], data[self.SRAM_WRITE_PKT_LEN*4:]
            chunk = np.fromstring(chunk, dtype='<u4')
            pkt = pktWriteSram(writeDerp, chunk)
            p.write(pkt.tostring())
            writeDerp += 1

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

    def clear(self, triggerCtx=None):
        """Create a packet to clear the ethernet buffer for this board."""
        p = self.makePacket().clear()
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        return p


    # board communication (can be called from within test mode)

    def _sendSRAM(self, data):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeSRAM(data, p)
        p.send()

    @inlineCallbacks
    def _sendRegisters(self, regs, readback=True, timeout=T.Value(10, 's')):
        """Send a register packet and optionally readback the result.

        If readback is True, the result packet is returned as a string of bytes.
        """
        if not isinstance(regs, np.ndarray):
            regs = np.asarray(regs, dtype='<u1')
        p = self.makePacket()
        p.write(regs.tostring())
        if readback:
            p.timeout(timeout)
            p.read()
        ans = yield p.send()
        if readback:
            src, dst, eth, data = ans.read
            returnValue(data)

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
                
                regs = regI2C(bytes, read, ack)
                r = yield self._sendRegisters(regs)
                ansBytes = processReadback(r)['I2Cbytes'][-len(data):] # readout data wrapped around to end
                
                answer += [b for b, r in zip(ansBytes, read) if r]
        returnValue(answer)

    @inlineCallbacks
    def _runSerial(self, op, data):
        """Run a command or list of commands through the serial interface."""
        answer = []
        for d in data:
            regs = regSerial(op, d)
            r = yield self._sendRegisters(regs)
            answer += [int(processReadback(r)['serDAC'])] # turn these into python ints, instead of numpy ints
        returnValue(answer)
    
    @inlineCallbacks
    def _setPolarity(self, chan, invert):
        regs = regClockPolarity(chan, invert)
        yield self._sendRegisters(regs)
        returnValue(invert)
    
    def testMode(self, func, *a, **kw):
        """Run a func in test mode on our board group."""
        return self.boardGroup.testMode(func, *a, **kw)
    
    
    # externally-accessible functions that put the board into test mode
    
    def buildNumber(self):
        @inlineCallbacks
        def func():
            regs = regPing()
            r = yield self._sendRegisters(regs)
            returnValue(str(processReadback(r)['build']))
        return self.testMode(func)

    def initPLL(self):
        @inlineCallbacks
        def func():
            yield self._runSerial(1, [0x1FC093, 0x1FC092, 0x100004, 0x000C11])
            regs = regRunSram(0, 0, loop=False) #Run sram with startAddress=endAddress=0. Run once, no loop.
            yield self._sendRegisters(regs, readback=False)
        return self.testMode(func)
        
    def queryPLL(self):
        @inlineCallbacks
        def func():
            regs = regPllQuery()
            r = yield self._sendRegisters(regs)
            returnValue(processReadback(r)['noPllLatch'])
        return self.testMode(func)
    
    def resetPLL(self):
        @inlineCallbacks
        def func():
            regs = regPllReset()
            yield self._sendRegisters(regs)
        return self.testMode(func)
    
    def debugOutput(self, word1, word2, word3, word4):
        @inlineCallbacks
        def func():
            pkt = regDebug(word1, word2, word3, word4)
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
    
            pkt = regRunSram(startAddr, endAddr, loop, blockDelay)
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
    
    def setLVDS(self, cmd, data):
        @inlineCallbacks
        def func():
            pkt = [[0x0400 + (i<<4), 0x8500, 0x0400 + i, 0x8500][j]
                   for i in range(16) for j in range(4)]
    
            if data is None:
                answer = yield self._runSerial(cmd, [0x0500] + pkt)
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
                t = (MHD-MSD)/2 & 0xF
            else:
                MSD = 0
                MHD = 0
                t = data & 0xF
    
            answer = yield self._runSerial(cmd, [0x0500 + (t<<4)] + pkt)
            answer = [(bool(answer[i*4+2] & 1), bool(answer[i*4+4] & 1))
                      for i in range(16)]
            returnValue((MSD, MHD, t, answer))
        return self.testMode(func)
    
    def setFIFO(self, chan, op):
        @inlineCallbacks
        def func():
            # set clock polarity to positive
            clkinv = False
            yield self._setPolarity(chan, clkinv)
    
            pkt = [0x0500, 0x8700] # set LVDS delay and read FIFO counter
            reading = yield self._runSerial(op, [0x8500] + pkt) # read current LVDS delay and exec pkt
            oldlvds = (reading[0] & 0xF0) | 0x0500 # grab current LVDS setting
            reading = reading[2] # get FIFO counter reading
            base = reading
            while reading == base: # until we have a clock edge ...
                pkt[0] += 16 # ... move LVDS
                if pkt[0] >= 0x0600:
                    raise Exception('Failed to find clock edge while setting FIFO counter!')
                reading = (yield self._runSerial(op, pkt))[1]
    
            pkt = [pkt[0] + 16*i for i in [2, 4]] # slowly step 6 clicks beyond edge to be centered on bit
            newlvds = pkt[-1]
            yield self._runSerial(op, pkt)
    
            tries = 5
            found = False
    
            while tries > 0 and not found:
                tries -= 1
                pkt =  [0x0700, 0x8700, 0x0701, 0x8700, 0x0702, 0x8700, 0x0703, 0x8700]
                reading = yield self._runSerial(op, pkt)
                reading = [(reading[i]>>4) & 0xF for i in [1, 3, 5, 7]]
                try:
                    PHOF = reading.index(3)
                    pkt = [0x0700 + PHOF, 0x8700]
                    reading = long(((yield self._runSerial(op, pkt))[1] >> 4) & 7)
                    found = True
                except Exception:
                    clkinv = not clkinv
                    yield self._setPolarity(chan, clkinv)
    
            if not found:
                raise Exception('Cannot find a FIFO offset to get a counter value of 3! Found: ' + repr(reading))
    
            # return to old lvds setting
            pkt = range(newlvds, oldlvds, -32)[1:] + [oldlvds]
            yield self._runSerial(op, pkt)
            ans = (oldlvds >> 4) & 0xF, (newlvds >> 4) & 0xF, clkinv, PHOF, reading
            returnValue(ans)
        return self.testMode(func)
    
    def runBIST(self, cmd, shift, dataIn):
        """Run a BIST on the given SRAM sequence. (DAC only)"""
        @inlineCallbacks
        def func():
            pkt = regRunSram(0, 0, loop=False)
            yield self._sendRegisters(pkt, readback=False)
    
            dat = [d & 0x3FFF for d in dataIn]
            data = [0, 0, 0, 0] + [d << shift for d in dat]
            # make sure data is at least 20 words long by appending 0's
            data += [0] * (20-len(data))
            data = np.array(data, dtype='<u4').tostring()
            yield self._sendSRAM(data)
            startAddr, endAddr = 0, len(data) / 4
            yield self._runSerial(cmd, [0x0004, 0x1107, 0x1106])
    
            pkt = regRunSram(startAddr, endAddr, loop=False)
            yield self._sendRegisters(pkt, readback=False)
    
            seq = [0x1126, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x1166, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11A6, 0x9200, 0x9300, 0x9400, 0x9500,
                   0x11E6, 0x9200, 0x9300, 0x9400, 0x9500]
            theory = tuple(bistChecksum(dat))
            bist = yield self._runSerial(cmd, seq)
            reading = [(bist[i+4] <<  0) + (bist[i+3] <<  8) +
                       (bist[i+2] << 16) + (bist[i+1] << 24)
                       for i in [0, 5, 10, 15]]
            lvds, fifo = tuple(reading[0:2]), tuple(reading[2:4])
    
            # lvds and fifo may be reversed.  This is okay
            lvds = lvds[::-1] if lvds[::-1] == theory else lvds
            fifo = fifo[::-1] if fifo[::-1] == theory else fifo
            returnValue((lvds == theory and fifo == theory, theory, lvds, fifo))
        return self.testMode(func)
    


def shiftSRAM(cmds, page):
    """Shift the addresses of SRAM calls for different pages.

    Takes a list of memory commands and a page number and
    modifies the commands for calling SRAM to point to the
    appropriate page.
    """
    def shiftAddr(cmd):
        opcode, address = getOpcode(cmd), getAddress(cmd)
        if opcode in [0x8, 0xA]: 
            address += page * self.SRAM_PAGE_LEN
            return (opcode << 20) + address
        else:
            return cmd
    return [shiftAddr(cmd) for cmd in cmds]

def getOpcode(cmd):
    return (cmd & 0xF00000) >> 20

def getAddress(cmd):
    return (cmd & 0x0FFFFF)

def bistChecksum(data):
    bist = [0, 0]
    for i in xrange(0, len(data), 2):
        for j in xrange(2):
            if data[i+j] & 0x3FFF != 0:
                bist[j] = (((bist[j] << 1) & 0xFFFFFFFE) | ((bist[j] >> 31) & 1)) ^ ((data[i+j] ^ 0x3FFF) & 0x3FFF)
    return bist

def parseHardwareParameters(parameters, device):
    for key,value in dict(parameters.)items():
        device[key]=value
    device.SRAM_WRITE_DERPS = device.SRAM_LEN / device.SRAM_WRITE_PKT_LEN

