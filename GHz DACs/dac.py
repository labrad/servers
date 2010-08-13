import numpy as np

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper


REG_PACKET_LEN = 56

READBACK_LEN = 70

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


def macFor(board):
    """Get the MAC address of a DAC board as a string."""
    return '00:01:CA:AA:00:' + ('0'+hex(int(board))[2:])[-2:].upper()

def isMac(mac):
    return mac.startswith('00:01:CA:AA:00:')


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



class DacDevice(DeviceWrapper):
    """Manages communication with a single GHz DAC board.

    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @inlineCallbacks
    def connect(self, de, port, board, build, name):
        """Establish a connection to the board."""
        print 'connecting to DAC board: %s (build #%d)' % (macFor(board), build)

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
        p = self.makePacket()
        p.connect(port)
        p.require_length(DAC_READBACK_LEN)
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()

    @inlineCallbacks
    def shutdown(self):
        yield self.cxn.manager.expire_context(self.server.ID, context=self.ctx)

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

    def clear(self, triggerCtx=None):
        """Create a packet to clear the ethernet buffer for this board."""
        p = self.makePacket().clear()
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        return p

    @inlineCallbacks
    def sendSRAM(self, data):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeSRAM(data, p)
        p.send()

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


