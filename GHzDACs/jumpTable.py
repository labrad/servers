# Author: Daniel Sank
# Created: July 2013

import numpy as np
from util import littleEndian

JUMP_INDEX_MIN = 1
JUMP_INDEX_MAX = 15
IDLE_MIN_CYCLES = 1
IDLE_MAX_CYCLES = (2**15)-1
DAISY_VALUE_MIN = 0
DAISY_VALUE_MAX = 15

NUM_COUNTERS = 4

SRAM_ADDR_MIN = 0
SRAM_ADDR_MAX = 8192 - 1 #XXX HACK ALERT! This should be imported from other module or registry!!!

# A single entry in the jump table

class JumpEntry(object):
    """A single entry in the jump table"""
    def __init__(self, fromAddr, toAddr, operation=None):
        self.fromAddr = fromAddr
        self.toAddr = toAddr
        self.operation = operation
    
    def getToAddr(self):
        return self._toAddr
    def setToAddr(self, addr):
        if SRAM_ADDR_MIN <= addr and addr <= SRAM_ADDR_MAX:
            self._toAddr = addr
        else:
            raise RuntimeError("Must have %s <= toAddr <= %s"%(SRAM_ADDR_MIN, SRAM_ADDR_MAX))
    toAddr = property(getToAddr, setToAddr)
    
    def getFromAddr(self):
        return self._fromAddr
    def setFromAddr(self, addr):
        if SRAM_ADDR_MIN <= addr and addr <= SRAM_ADDR_MAX:
            self._fromAddr = addr
        else:
            raise RuntimeError("Must have %s <= fromAddr <= %s"%(SRAM_ADDR_MIN, SRAM_ADDR_MAX))
    fromAddr = property(getFromAddr, setFromAddr)
    
    def __str__(self):
        fromAddrStr = "fromAddr: %d"%self.fromAddr
        toAddrStr = "toAddr: %d"%self.toAddr
        opStr = str(self.operation)
        return '\n'.join([fromAddrStr, toAddrStr, opStr])
    
    def asBytes(self):
        data = np.zeros(8,dtype='<u1')
        data[0:3] = littleEndian(self.fromAddr, 3)
        data[3:6] = littleEndian(self.toAddr, 3)
        data[6:8] = littleEndian(self.operation.asBytes(), 2)
        return data

# Operations (ie op codes)
        
class Operation(object):
    """A Super class for all possible jump table operations"""
    def getJumpIndex(self):
        return self._jumpIndex
    def setJumpIndex(self, idx):
        if JUMP_IDX_MIN < idx and idx < JUMP_IDX_MAX:
            self._jumpIndex = idx
        else:
            raise RuntimeError("Must have %s < jump index < %s"%(JUMP_INDEX_MIN, JUMP_INDEX_MAX))
    jumpIndex = property(getJumpIndex, setJumpIndex)
    
    def __str__(self):
        raise NotImplementedError
    
    def asBytes(self):
        """Override in subclass"""
        raise NotImplementedError

class IDLE(Operation):
    """Wraps the IDLE jump table op code"""
    
    NAME = "IDLE"
    
    def __init__(self, cycles):
        self._cycles = cycles
    
    def getJumpIndex(self):
        raise RuntimeError('IDLE does not support jump table indexing')
    def setJumpIndex(self, idx):
        raise RuntimeError('IDLE does not support jump table indexing')
    
    def getCycles(self):
        return self._cycles
    def setCycles(self, cycles):
        if IDLE_MIN_CYCLES < cycles and cycles < IDLE_MAX_CYCLES:
            self._cycles = cycles
        else:
            raise RuntimeError('Number of idle cycles must satisfy: %s < cycles < %s'%(IDLE_MIN_CYCLES,IDLE_MAX_CYCLES))
    cycles = property(getCycles, setCycles)
    
    def __str__(self):
        return "%s %d cycles"%(self.NAME, self.cycles)
    
    def asBytes(self):
        return self._cycles<<1
    
class CHECK(Operation):

    NAME = "CHECK"
    
    def __init__(self, whichDaisyBit, bitOnOff, nextJumpIndex):
        raise RuntimeError('CHECK is not yet understood')
        self.whichDaisyBit = whichDaisyBit
        self.jumpIndex = nextJumpIndex
        self.bitOnOff = bool(bitOnOff)
        
    def getWhichDaisyBit(self):
        return self._whichDaisyBit
    def setWhichDaisyBit(self, whichBit):
        if DAISY_VALUE_MIN < whichBit and whichBit < DAISY_VALUE_MAX:
            self._whichDaisyBit = whichBit
        else:
            raise RuntimeError("Must have %s < daisy whichDaisyBit < %s"%(DAISY_VALUE_MIN, DAISY_VALUE_MAX))
    whichDaisyBit = property(getWhichDaisyBit, setWhichDaisyBit)
    
    def asBytes(self):
        #Op code is 001, so shift 4 bits and add 1
        return self.jumpIndex<<8 + self.whichDaisyBit<<4 + int(self.bitOnOff)<<3 + 1

class JUMP(Operation):

    NAME = "JUMP"

    def __init__(self, nextJumpIndex):
        self.jumpIndex = nextJumpIndex
    
    def __str__(self):
        return '\n'.join([self.NAME, "Next jump index: %d"%self.jumpIndex])
        
    def asBytes(self):
        #Op code is 1101 = 13
        return self.jumpIndex<<8 + 13
    
class NOP(Operation):

    NAME = "NOP"
    
    def __str__(self):
        return self.NAME
    
    def asBytes(self):
        return 0x0005
    
class CYCLE(Operation):
    def __init__(self, count, nextJumpIndex):
        self.count = count
        self.jumpIndex = nextJumpIndex
    
    def getWhichCounter(self):
        return self._whichCounter
    def setWhichCounter(self, whichCounter):
        if 0 <= whichCounter and whichCount < NUM_COUNTERS:
            self._whichCounter = whichCounter
        else:
            raise RuntimeError("Must have %s < whichCounter < %s"%(0, NUM_COUNTERS))
    whichCounter = property(getWhichCounter, setWhichCounter)
    
    def asBytes(self):
        return self.jumpIndex<<8 + self.whichCounter<<4 + 3
    
class END(object):

    NAME = "END"
    
    def __str__(self):
        return self.NAME
    
    def asBytes(self):
        return 7

# The actual jump table
        
class JumpTable(object):
    """
    The entire jump table.
    
    This is a very low level wrapper around the actual FPGA data structure
    
    TODO: make self.jumps a property with some checking on type and number
    """
    PACKET_LEN = 528
    COUNT_MAX = 2**32 - 1 #32 bit register for counters
    
    def __init__(self, startAddr=None, jumps=None):
        self._counters = [0,0,0,0]        
        self.startAddr = startAddr
        self.jumps = jumps
    
    def getStartAddr(self):
        return self._startAddr
    def setStartAddr(self, addr):
        if SRAM_ADDR_MIN <= addr and addr <= SRAM_ADDR_MAX:
            self._startAddr = addr
        else:
            raise RuntimeError("Must have %s <= start addr <= %s" %(SRAM_ADDR_MIN, SRAM_ADDR_MAX))
    startAddr = property(getStartAddr, setStartAddr)
    
    #TODO: error check counter values
    
    def __str__(self):
        counterStr = '\n'.join("Counter %d: %d"%(i,c) for i,c in enumerate(self._counters))
        startAddrStr = 'Start address: %d'%self.startAddr
        jumpsStr = '\n'.join("-JUMP ENTRY %d-\n%s"%(i,str(jump)) for i,jump in enumerate(self.jumps))
        return '\n'.join([counterStr, startAddrStr, jumpsStr])
        
    def toString(self):
        """Write a byte string for the FPGA"""
        data = np.zeros(self.PACKET_LEN, dtype='<u1')
        #Set counter maxima. Each one is 4 bytes
        for i,c in enumerate(self._counters):
            data[i*4:(i+1)*4] = littleEndian(c, 4)
        
        #Set start address
        data[16:19] = littleEndian(self.startAddr,3)
        data[19:22] = littleEndian(self.startAddr,3)
        #Start op code
        data[22] = 5
        data[23] = 0
        for i, jump in enumerate(self.jumps):
            data[24+(i*8):24+((i+1)*8)] = jump.asBytes()
        
        return data.tostring()
        
# Unit tests

def testNormal(stopAddr):
    #SRAM steps from 0 to 1020 over 256 ns.
    #Verticle step size is 4 DAC clicks per sample
    waveform = np.zeros(256)*1.0
    waveform = ([0]*8 + [1]*8)*16
    
    jumpEntries = []
    
    #End execution
    op = END()
    fromAddr = stopAddr
    toAddr = 0 #Meaningless?
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))
    
    table = JumpTable(0)
    table.jumps = jumpEntries
    
    return waveform, table

def testIdle(cycles):
    """
    Single high sample, followed by idle, followed by single high sample
    
    RETURNS - (sramBlock, table)
     sramBlock - ndarray: numerical SRAM data, not packed as bytes
     table - JumpTable: jump table object
    """
    #The SRAM block we use to store data
    #0          10       20        30
    #   |   |   |   |   |   |   |   |   |   |
    #0123456789012345678901234567890123456789
    #___________-____________________-_______
    
    waveform = np.zeros(256)
    waveform[11] = 1    #This is at the end of a 4 word block
    waveform[32] = 1    #This is at the start of a 4 word block
    
    jumpEntries = []
    
    #Jump from first SRAM section to second one
    #Run SRAM words 0..11, idle 25 cycles, run words 32..35
    op = IDLE(cycles)
    fromAddr = 5
    toAddr = 0 #Meaningless?
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))
    
    #End execution
    op = END()
    fromAddr = 40
    toAddr = 0 #Meaningless?
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))
    
    table = JumpTable(0)
    table.jumps = jumpEntries
    
    return waveform, table