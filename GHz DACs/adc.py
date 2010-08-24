import numpy as np

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock

DEMOD_CHANNELS = 4
DEMOD_PACKET_LEN = 46 # length of result packets in demodulation mode
AVERAGE_PACKETS = 32 # number of packets that
AVERAGE_PACKET_LEN = 1024

TRIG_AMP = 255
REG_PACKET_LEN = 59
READBACK_LEN = 46
FILTER_LEN = 4096
SRAM_WRITE_PAGES = 9
SRAM_WRITE_LEN = 1024


def macFor(board):
    """Get the MAC address of an ADC board as a string."""
    return '00:01:CA:AA:01:' + ('0'+hex(int(board))[2:])[-2:].upper()

def isMac(mac):
    return mac.startswith('00:01:CA:AA:01:')


# functions to register packets for ADC boards

def regAdcPing():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs

def regAdcPllQuery():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs

def regAdcSerial(bits):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 6
    regs[3:6] = littleEndian(bits, 3)
    return regs

def regAdcRecalibrate():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 7
    return regs

def regAdcRun(mode, reps, filterFunc, filterStretchAt, filterStretchLen, demods):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = mode # average mode, autostart
    regs[7:9] = littleEndian(reps, 2)
    
    regs[9:11] = littleEndian(len(filterFunc), 2)
    regs[11:13] = littleEndian(filterStretchAt, 2)
    regs[13:15] = littleEndian(filterStretchLen, 2)
    
    for i in range(DEMOD_CHANNELS):
        if i not in demods:
            continue
        addr = 15 + 4*i
        regs[addr:addr+2] = littleEndian(demods[i]['dphi'], 2)
        regs[addr+2:addr+4] = littleEndian(demods[i]['phi0'], 2)
    return regs


def processReadback(resp):
    a = np.fromstring(resp, dtype='<u1')
    return {
        'build': a[0],
        'noPllLatch': bool(a[1] > 0),
    }

def pktWriteSram(page, data):
    assert 0 <= page < SRAM_WRITE_PAGES, 'SRAM page out of range: %d' % page 
    data = np.asarray(data)
    pkt = np.zeros(1026, dtype='<u1')
    pkt[0:2] = littleEndian(page, 2)
    pkt[2:2+len(data)] = data
    return pkt


# wrapper that actually talks to the device

class AdcDevice(DeviceWrapper):
    """Manages communication with a single GHz ADC board.
    
    All communication happens through the direct ehternet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @inlineCallbacks
    def connect(self, name, de, port, board, build):
        """Establish a connection to the board."""
        print 'connecting to ADC board: %s (build #%d)' % (macFor(board), build)

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
        self.boardLock = TimedLock

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
    
    @inlineCallbacks
    def shutdown(self):
        yield self.cxn.manager.expire_context(self.server.ID, context=self.ctx)
    
    def makePacket(self):
        """Create a new packet to be sent to the ethernet server for this device."""
        return self.server.packet(context=self.ctx)
    
    def makeFilter(self, data, p):
        """Update a packet for the ethernet server with SRAM commands to upload the filter function."""
        for page in range(4):
            start = SRAM_WRITE_LEN * page
            end = start + SRAM_WRITE_LEN
            pkt = pktWriteSram(page, data[start:end])
            p.write(pkt.tostring())
    
    def makeTrigLookups(self, demods, p):
        """Update a packet for the ethernet server with SRAM commands to upload Trig lookup tables."""
        page = 4
        channel = 0
        while channel < DEMOD_CHANNELS:
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
            pkt = pktWriteSram(page, data)
            p.write(pkt.tostring())            
            channel += 2 # two channels per sram packet
            page += 1 # each sram packet writes one page

    def clear(self, triggerCtx=None):
        """Create a packet to clear the ethernet buffer for this board."""
        p = self.makePacket().clear()
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        return p

    
    @inlineCallbacks
    def sendSRAM(self, filter, demods={}):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        yield p.send()
    
    
    @inlineCallbacks
    def sendRegisters(self, regs, readback=True, timeout=T.Value(10, 's')):
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
    def runSerial(self, data):
        """Run a command or list of commands through the serial interface."""
        for d in data:
            regs = regAdcSerial(d)
            yield self.sendRegisters(regs, readback=False)
    
    @inlineCallbacks
    def doWithLock(self, func, *a, **kw):
        try:
            yield self.boardLock.acquire()
            yield func(*a, **kw)
        finally:
            self.boardLock.release()
    
    
    # chatty functions that require locking the device
    
    def recalibrate(self):
        @inlineCallbacks
        def func():
            regs = regAdcRecalibrate()
            yield self.sendRegisters(regs, readback=False)
        return self.doWithLock(func)
    
    def initPLL(self):
        @inlineCallbacks
        def func():
            yield self.runSerial([0x1FC093, 0x1FC092, 0x100004, 0x000C11])
        return self.doWithLock(func)
    
    def queryPLL(self):
        @inlineCallbacks
        def func():
            regs = regAdcPllQuery()
            r = yield self.sendRegisters(regs)
            returnValue(processReadback(r)['noPllLatch'])
        return self.doWithLock(func)
        
    def runAverage(self, filterFunc, filterStretchLen, filterStretchAt, demods):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = regAdcRun(2, 1, filterFunc, filterStretchLen, filterStretchAt, demods)
    
            # create packet for the ethernet server
            p = self.makePacket()
            self.makeFilter(filterFunc, p) # upload filter function
            self.makeTrigLookups(demods, p) # upload trig lookup tables
            p.write(regs.tostring()) # send registry packet
            p.timeout(T.Value(10, 's')) # set a conservative timeout
            p.read(AVERAGE_PACKETS) # read back all packets from average buffer
            
            ans = yield p.send()
                    
            # parse the packets out and return data
            vals = []
            for src, dst, eth, data in ans.read:
                vals.append(np.fromstring(data, dtype='<i2'))
            Is, Qs = np.hstack(vals).reshape(-1, 2).astype(int).T
            returnValue((Is, Qs))
        return self.doWithLock(func)
        
    
    def runDemod(self, filterFunc, filterStretchLen, filterStretchAt, demods):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = regAdcRun(4, 1, filterFunc, filterStretchLen, filterStretchAt, demods)
    
            # create packet for the ethernet server
            p = self.makePacket()
            self.makeFilter(filterFunc, p) # upload filter function
            self.makeTrigLookups(demods, p) # upload trig lookup tables
            p.write(regs.tostring()) # send registry packet
            p.timeout(T.Value(10, 's')) # set a conservative timeout
            p.read(1) # read back one demodulation packet
            
            ans = yield p.send()
                    
            # parse the packets out and return data
            src, dst, eth, data = ans.read[0]
            vals = np.fromstring(data[:44], dtype='<i2')
            Is, Qs = vals.reshape(-1, 2).astype(int).T
            Irng, Qrng = [ord(i) for i in data[46:48]]
            twosComp = lambda i: int(i if i < 0x8 else i - 0x10)
            Imax = twosComp((Irng >> 4) & 0xF) # << 12
            Imin = twosComp((Irng >> 0) & 0xF) # << 12
            Qmax = twosComp((Qrng >> 4) & 0xF) # << 12
            Qmin = twosComp((Qrng >> 0) & 0xF) # << 12
            returnValue((Is, Qs, (Imax, Imin, Qmax, Qmin)))
        return self.doWithLock(func)

