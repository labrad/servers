import numpy as np

# Named functions
from labrad.devices import DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.units import Value

REGISTRY = {}

class FPGA(DeviceWrapper):
    """Manages communication with a single GHz FPGA board.
    
    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @classmethod
    def macFor(cls, board):
        """Get MAC address for a board as a string"""
        raise NotImplementedError
    
    @classmethod
    def isMac(cls, mac):
        """Returns True if mac is this type of FPGA board"""
        raise NotImplementedError
    
    # Methods to get bytes to be written to register
    # None of these are implemented here and must be implemented in
    # subclasses.
    # The definitions here are for documentation only.
    
    @classmethod
    def regPing(cls):
        """Returns a numpy array of register bytes to ping FPGA register"""
        raise NotImplementedError
    
    @classmethod
    def regPllQuery(cls):
        """Returns a numpy array of register bytes to query PLL status"""
        raise NotImplementedError
    
    @classmethod
    def regSerial(cls, bits):
        """
        Returns a numpy array of register bytes to write to bits to the PLL
        using the serial interace
        """
        raise NotImplementedError
    
    @classmethod
    def regRun(cls):
        """Returns a numpy array of register bytes to run the board"""
        raise NotImplementedError
    
    # Methods to get bytes to write data to the board
    # Must be implemented in subclass
    
    @classmethod
    def pktWriteSram(cls, derp, data):
        """Get a numpy array of bytes to write one derp of SRAM data"""
        raise NotImplementedError
    
    # Life cycle methods
    # Must be implemented in subclass
    
    @inlineCallbacks
    def connect():
        """Set up connection to this board"""
        raise NotImplementedError
    
    @inlineCallbacks
    def shutdown():
        """Close connection with this board"""
        raise NotImplementedError
    
    # Direct ethernet packet creation methods.
    # These probably do not need to be overridden in subclasses.
    
    def makePacket(self):
        """Create a direct ethernet server request packet for this device"""
        return self.server.packet(context=self.ctx)
    
    def collect(self, nPackets, timeout, triggerCtx=None):
        """
        Create a direct ethernet server request to collect data on the FPGA.
        
        Note that if the collect times out, the triggers are NOT sent.
        """
        p = self.makePacket()
        p.timeout(Value(timeout, 's'))
        p.collect(nPackets)
        # If a timeout error occurs the remaining records in the direct
        # ethernet server packet are not executed. In the present case this
        # means that if the timeout fails the trigger command will not be
        # sent. This really really REALLY bad programming but I don't want to
        # learn Delphi to fix the direct ethernet server. Just be happy that I
        # put this note here so you know what's going on.
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        return p
    
    def trigger(self, triggerCtx):
        """
        Create a direct ethernet server request to trigger the board group
        context.
        """
        return self.makePacket().send_trigger(triggerCtx)
    
    def read(self, nPackets):
        """
        Create a direct ethernet server request to read data for this FPGA.
        """
        return self.makePacket().read(nPackets)
    
    def discard(self, nPackets):
        """
        Create a direct ethernet server request that discards packets for this
        board.
        """
        return self.makePacket().discard(nPackets)
    
    def clear(self, triggerCtx=None):
        """
        Create a direct ethernet server request to clear the ethernet buffer
        for this board.
        """
        p = self.makePacket().clear()
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        return p
    
    def regPingPacket(self):
        """
        Create a direct ethernet server request that pings the board
        register.
        """
        regs = self.regPing()
        return self.makePacket().write(regs.tostring())
    
    # Board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _sendRegisters(self, regs, readback=True, timeout=Value(10, 's')):
        """
        Send a register packet and optionally readback the result.
        
        If readback is True, the result packet is returned as a string (of
        bytes).
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
    
    def _runSerial(self):
        """Send data to serial interface"""
        raise NotImplementedError
    
    # Externally available board interaction functions.
    # These run in test mode.
    
    def buildNumber(self):
        """Get build number"""
        @inlineCallbacks
        def func():
            regs = self.regPing()
            r = yield self._sendRegisters(regs)
            returnValue(str(self.processReadback(r)['build']))
        return self.testMode(func)
    
    def executionCount(self):
        """Get number of executions since last start"""
        @inlineCallbacks
        def func():
            regs = self.regPing()
            r = yield self._sendRegisters(regs)
            returnValue(self.processReadback(r)['executionCounter'])
        return self.testMode(func)
    
    def queryPLL(self):
        """Check PLL lock condition, True means unlock"""
        @inlineCallbacks
        def func():
            regs = self.regPllQuery()
            r = yield self._sendRegisters(regs)
            returnValue(self.processReadback(r)['noPllLatch'])
        return self.testMode(func)
    
    def initPLL(self):
        """Initialize PLL chip"""
        raise NotImplementedError
    
    # Utility methods
    
    @classmethod
    def processReadback(cls, resp):
        """Interpret byte string returned by register readback"""
        raise NotImplementedError
    
    def testMode(self, func, *a, **kw):
        """
        Run a func in test mode on our board group.
        
        Test mode acquires locks so that other operations on the board group,
        eg. data taking, are halted until the test operation completes.
        """
        return self.boardGroup.testMode(func, *a, **kw)


class ADC(FPGA):
    """
    Base class for ADC builds
    
    Most of the functions defined here are not implemented. The idea is to
    subclass this in classes specific to the various firmware/hardware builds.
    
    Some functions are implemented here. I chose to do this in a few functions
    that I don't expect to change. Of course you can just override them in
    subclasses as necessary.
    """
    
    MAC_PREFIX = '00:01:CA:AA:01:'
    REG_PACKET_LEN = 59
    READBACK_LEN = 46
    
    # Start modes
    RUN_MODE_AVERAGE_AUTO = 2
    RUN_MODE_AVERAGE_DAISY = 3
    RUN_MODE_DEMOD_AUTO = 4
    RUN_MODE_DEMOD_DAISY = 5
    RUN_MODE_CALIBRATE = 7
    
    @classmethod
    def macFor(cls, boardNumber):
        """Get the MAC address of an ADC board as a string."""
        return cls.MAC_PREFIX + ('0'+hex(int(boardNumber))[2:])[-2:].upper()
    
    @classmethod
    def isMac(mac):
        """Return True if this mac is for an ADC, otherwise False"""
        return mac.startswith(cls.MAC_PREFIX)
    
    # Life cycle methods
    
    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """Establish a connection to the board."""
        print('connecting to ADC board: %s (build #%d)'\
            % (self.macFor(board), build))

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

        # Set up our context with the ethernet server.
        # This context is expired when the device shuts down.
        p = self.makePacket()
        p.connect(port)
        # ADC boards send packets with different lengths:
        # - register readback: 46 bytes
        # - demodulator output: 48 bytes
        # - average readout: 1024 bytes
        # so we do not require a specific length for received packets.
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        #p.source_mac(self.boardGroup.sourceMac)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()
    
    @inlineCallbacks
    def shutdown(self):
        """Called when this device is to be shutdown."""
        yield self.cxn.manager.expire_context(self.server.ID,
                                              context=self.ctx)
    
    # Register byte methods
    
    @classmethod
    def regPing(cls):
        """Returns a numpy array of register bytes to ping ADC register"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1
        return regs
    
    @classmethod
    def regPllQuery(cls):
        """Returns a numpy array of register bytes to query PLL status"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1
        return regs
    
    @classmethod
    def regSerial(cls, bits):
        """Returns a numpy array of register bytes to write to PLL"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 6
        regs[3:6] = littleEndian(bits, 3)
        return regs
    
    @classmethod
    def regAdcRecalibrate(cls):
        """Returns a numpy array of register bytes to recalibrate ADC chips"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 7
        return regs
    
    # Methods to get byte arrays to be written to the board
    
    @classmethod
    def pktWriteSram(cls, derp, data):
        """Get a numpy array of bytes to write one derp of SRAM"""
        assert 0 <= derp < cls.SRAM_WRITE_DERPS, \
            'SRAM derp out of range: %d' % derp 
        data = np.asarray(data)
        pkt = np.zeros(cls.SRAM_WRITE_PKT_LEN, dtype='<u1')
        pkt[0:2] = littleEndian(derp, 2)
        pkt[2:2+len(data)] = data
        return pkt
    
    # Utility
    
    @staticmethod
    def readback2BuildNumber(resp):
        """Get build number from register readback"""
        a = np.fromstring(resp, dtype='<u1')
        return a[0]


class DAC(FPGA):
    
    MAC_PREFIX = '00:01:CA:AA:00:'
    REG_PACKET_LEN = 56
    READBACK_LEN = 70
    
    # Master delay before SRAM to ensure synchronization
    MASTER_SRAM_DELAY = 2 # microseconds

    @classmethod
    def macFor(cls, board):
        """Get the MAC address of a DAC board as a string."""
        return cls.MAC_PREFIX + ('0'+hex(int(board))[2:])[-2:].upper()
    
    @classmethod
    def isMac(mac):
        """Return True if this mac is for a DAC, otherwise False"""
        return mac.startswith('00:01:CA:AA:00:')
    
    # Register byte methods
    
    @classmethod
    def regPing(cls):
        """Returns a numpy array of register bytes to ping DAC register"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0 # No sequence start
        regs[1] = 1 # Readback after 2us
        return regs 
    
    @classmethod
    def regPllQuery(cls):
        """Returns a numpy array of register bytes to query PLL status"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1 # No sequence start
        regs[1] = 1 # Readback after 2us
        return regs
    
    @classmethod
    def regSerial(cls, op, data):
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0 #Start mode = no start
        regs[1] = 1 #Readback = readback after 2us to allow for serial
        regs[47] = op #Set serial operation mode to op
        regs[48:51] = littleEndian(data, 3) #Serial data
        return regs
    
    @classmethod
    def regPllReset(cls):
        """Send reset pulse to 1GHz PLL"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 0
        regs[1] = 1
        regs[46] = 0x80 #Set d[7..0] to 10000000 = reset 1GHz PLL pulse
        return regs
    
    def resetPLL(self):
        """Reset PLL"""
        raise NotImplementedError
    
    # Utility
    
    @staticmethod
    def readback2BuildNumber(resp):
        """Get build number from register readback"""
        a = np.fromstring(resp, dtype='<u1')
        return a[51]
    
    def parseBoardParameters(self, parametersFromRegistry):
        """Handle board specific data retreived from registry"""
        for key, val in dict(parametersFromRegistry).items():
            self.__dict__[key] = val
    
    @staticmethod
    def bistChecksum(data):
        bist = [0, 0]
        for i in xrange(0, len(data), 2):
            for j in xrange(2):
                if data[i+j] & 0x3FFF != 0:
                    bist[j] = (((bist[j] << 1) & 0xFFFFFFFE) | \
                              ((bist[j] >> 31) & 1)) ^ \
                              ((data[i+j] ^ 0x3FFF) & 0x3FFF)
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

