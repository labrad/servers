import numpy as np

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock

def macFor(board):
    """Get the MAC address of an ADC board as a string."""
    return '00:01:CA:AA:01:' + ('0'+hex(int(board))[2:])[-2:].upper()

def isMac(mac):
    return mac.startswith('00:01:CA:AA:01:')
    
def regPing():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs    
    
class DeviceClass(DeviceWrappers):
    """Manages communication with a single GHz FPGA board.
    
    All communication happens through the direct ethernet server,
    and we set up one unique context to use for talking to each board.
    """
    
        # lifecycle functions for this device wrapper
    
    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """
        Establish a connection to the board.
        
        This method must be overloaded
        """       
        raise Exception
        
        
    @inlineCallbacks
    def shutdown(self):
        """Called when this device is to be shutdown."""
        yield self.cxn.manager.expire_context(self.server.ID, context=self.ctx)

    def makePacket(self):
        """Create a new packet to be sent to the ethernet server for this device."""
        return self.server.packet(context=self.ctx)

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
        
    #board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _sendSRAM(self, filter, demods={}):
        """
        Write SRAM data to the FPGA.
        
        This method must be overloaded.
        """
        
        raise Excepetion
        
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
    def _runSerial(self, data):
        """
        Run a command or list of commands through the serial interface.
        
        This method must be overloaded
        """
        
        raise Exception
        
    def testMode(self, func, *a, **kw):
        """Run a func in test mode on our board group."""
        return self.boardGroup.testMode(func, *a, **kw)            
        
    # chatty functions that require locking the device
    
    def initPLL(self):
        """This method must be overloaded"""
        
        raise Exception
        
    def queryPLL(self):
        @inlineCallbacks
        def func():
            regs = regAdcPllQuery()
            r = yield self._sendRegisters(regs)
            returnValue(processReadback(r)['noPllLatch'])
        return self.testMode(func)    

    def buildNumber(self):
        @inlineCallbacks
        def func():
            regs = regPing()
            r = yield self._sendRegisters(regs)
            returnValue(str(processReadback(r)['build']))
        return self.testMode(func)        

#Shared functions:
# macFor
# isMac
# regPing
