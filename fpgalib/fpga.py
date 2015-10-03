import numpy as np
import os

# Named functions
from labrad.devices import DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.units import Value
from fpgalib.util import LoggingPacket

# A registry of FPGA board classes. The class for each build must be added to
# this registry so that the fpga server knows what type of object to construct
# for each detected hardware board.
REGISTRY = {}  # (Board type, build number) -> Class


# Safety factor for timeout estimates
TIMEOUT_FACTOR = 10

USE_LOGGING_PACKETS = False


class FPGA(DeviceWrapper):
    """Manages communication with a single GHz FPGA board.
    
    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
    @classmethod
    def macFor(cls, board):
        """Get MAC address for a board as a string"""
        raise NotImplementedError()
    
    @classmethod
    def isMac(cls, mac):
        """Returns True if mac is this type of FPGA board"""
        raise NotImplementedError()
    
    # Methods to get bytes to be written to register
    # None of these are implemented here and must be implemented in
    # subclasses.
    # The definitions here are for documentation only.
    
    @classmethod
    def regPing(cls):
        """Returns a numpy array of register bytes to ping FPGA register"""
        raise NotImplementedError()
    
    @classmethod
    def regPllQuery(cls):
        """Returns a numpy array of register bytes to query PLL status"""
        raise NotImplementedError()
    
    @classmethod
    def regSerial(cls, bits):
        """
        Returns a numpy array of register bytes to write to bits to the PLL
        using the serial interace
        """
        raise NotImplementedError()
    
    @classmethod
    def regRun(cls):
        """Returns a numpy array of register bytes to run the board"""
        raise NotImplementedError()
    
    # Methods to get bytes to write data to the board
    # Must be implemented in subclass
    
    @classmethod
    def pktWriteSram(cls, derp, data):
        """Get a numpy array of bytes to write one derp of SRAM data"""
        raise NotImplementedError()
    
    # Life cycle methods
    # Must be implemented in subclass
    
    @inlineCallbacks
    def connect(*args, **kwargs):
        """Set up connection to this board"""
        raise NotImplementedError()
    
    @inlineCallbacks
    def shutdown(*args, **kwargs):
        """Close connection with this board"""
        raise NotImplementedError()
    
    # Direct ethernet packet creation methods.
    # These probably do not need to be overridden in subclasses.
    
    def _makePacket(self, ignore=None):
        """Create a direct ethernet server request packet for this device"""
        return self.server.packet(context=self.ctx)
    
    def makeLoggingPacket(self, name=None):
        """Create a direct ethernet server request packet with tracing"""
        p = self._makePacket()
        return LoggingPacket(p, name)
    
    if USE_LOGGING_PACKETS:
        makePacket = makeLoggingPacket
    else:
        makePacket = _makePacket

    def collect(self, nPackets, timeout, triggerCtx=None):
        """
        Create a direct ethernet server request to collect data on the FPGA.
        
        Note that if the collect times out, the triggers are NOT sent.
        """
        p = self.makePacket()
        # print('fpga.py: collect: timeout = %s, waiting for nPackets: %s'%(timeout,nPackets))
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
            p.read(1)
        ans = yield p.send()
        if readback:
            src, dst, eth, data = ans.read[0]
            returnValue(data)
    
    def _runSerial(self):
        """Send data to serial interface"""
        raise NotImplementedError()
    
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
        raise NotImplementedError()
    
    # Utility methods
    
    @classmethod
    def processReadback(cls, resp):
        """Interpret byte string returned by register readback"""
        raise NotImplementedError()
    
    def testMode(self, func, *a, **kw):
        """
        Run a func in test mode on our board group.
        
        Test mode acquires locks so that other operations on the board group,
        eg. data taking, are halted until the test operation completes.
        """
        return self.boardGroup.testMode(func, *a, **kw)
