# Author: Daniel Sank
# Created: July 2013

#Unit testing
# Check that all idle values actually work, ie can we use all bits?

from util import littleEndian

JUMP_INDEX_MIN = 1
JUMP_INDEX_MAX = 15
IDLE_MIN_CYCLES = 1
IDLE_MAX_CYCLES = (2**15)-1
DAISY_VALUE_MIN = 0
DAISY_VALUE_MAX = 15

class JumpEntry(object):
    def __init__(self, fromAddr, toAddr, operation):
        self.fromAddr = fromAddr
        self.toAddr = toAddr
        self.operation = operation

class Operation(object):
    def getJumpIndex(self):
        return self._jumpIndex
    def setJumpIndex(self, idx):
        if JUMP_IDX_MIN < idx and idx < JUMP_IDX_MAX:
            self._jumpIndex = idx
        else:
            raise RuntimeError("Must have %s<jump index<%s"%(JUMP_INDEX_MIN, JUMP_INDEX_MAX))
    jumpIndex = property(getJumpIndex, setJumpIndex)
    
    def asBytes(self):
        raise NotImplementedError

class IDLE(Operation):
    """Wraps the IDLE jump table op code"""
    def __init__(self, cycles):
        self._cycles = cycles
    
    def getJumpIndex(self):
        raise RuntimeError('IDLE does not support jump table indexing')
    def setJumpIndex(self, idx):
        raise RuntimeError('IDLE does not support jump table indexing')
    
    def getIdleCycles(self):
        return self._cycles
    def setIdleCycles(self, cycles):
        if IDLE_MIN_CYCLES < cycles and cycles < IDLE_MAX_CYCLES:
            self._cycles = cycles
        else:
            raise RuntimeError('must have %s<IDLE cycles<%s'%(IDLE_MIN_CYCLES,IDLE_MAX_CYCLES))
    cycles = property(getIdleCycles, setIdleCycles)
    
    def asBytes(self):
        return self._cycles<<1
    
class CHECK(Operation):
    def __init__(self, whichDaisyBit, bitOnOff, nextJumpIndex):
        self.whichDaisyBit = whichDaisyBit
        self.jumpIndex = nextJumpIndex
        self.bitOnOff = bool(bitOnOff)
        
    def getWhichDaisyBit(self):
        return self._whichDaisyBit
    def setCheckValue(self, whichBit):
        if DAISY_VALUE_MIN < whichBit and whichBit < DAISY_VALUE_MAX:
            self._whichDaisyBit = whichBit
        else:
            raise RuntimeError('Must have %s<daisy whichDaisyBit<%s'%(DAISY_VALUE_MIN, DAISY_VALUE_MAX))
    whichDaisyBit = property(getWhichDaisyBit, setWhichDaisyBit)
    
    def asBytes(self):
        #Op code is 001, so shift 4 bits and add 1
        return self.jumpIndex<<8 + self.whichDaisyBit<<4 + int(self.bitOnOff)<<3 + 1

class JUMP(Operation):
    def __init__(self, nextJumpIndex):
        self.jumpIndex = nextJumpIndex

    def asBytes(self):
        return self.jumpIndex<<8 + 13
    
class NOP(Operation):
    def asBytes(self):
        return 0x0005
    
class CYCLE(Operation):
    def __init__(self, count, nextJumpIndex):
        self.count = count
        self.jumpIndex = nextJumpIndex
    
    def getCount(self):
        return self._count
    def setCount(self, count):
        if CYCLE_COUNT_MIN < count and count < CYCLE_COUNT_MAX:
            self._count = count
        else:
            raise RuntimeError("Must have %s < cycle count < %s"%(CYCLE_COUNT_MIN, CYCLE_COUNT_MAX))
    count = property(getCount, setCount)
    
    def asBytes(self):
        return self.jumpIndex<<8 + self._count<<4 + 3
    
class END(object):
    def asBytes(self):
        return 7
        
class JumpTable(object):
    
    PACKET_LEN = 144
    COUNTER_BYTES = 4
    MAX_COUNT = 2**COUNTER_BYTES - 1
    NUM_COUNTERS = 4
    NUM_JUMPS = 15
    
    def __init__(self):
        self.counters = [0]*NUM_COUNTERS
        
    def setCounter(self, whichCounter, count):
        assert count < self.MAX_COUNT
        self.counters[whichCounter] = count
    
    def dumps(self):
        """Write a byte string for the FPGA"""
        data = np.zeros(self.PACKET_LEN)
        for counter in range(self.NUM_COUNTERS):
            data[counter*4:(counter+1)*4] = littleEndian(self.counters[counter],4)
        #Set start address
        data[16:19] = littleEndian(self.startAddr,3)
        data[20:23] = littleEndian(self.startAddr,3)
        #Start op code
        data[22] = 5
        data[23] = 0
        for i, jump in enumerate(self.jumps):
            idx = i+24
            data[idx:idx+3] = littleEndian(jump.fromAddr, 3)
            idx += 3
            data[idx:idx+3] = littleEndian(jump.toAddr, 3)
            idx += 3
            data[idx:idx+2] = littleEndian(jump.opCode, 2)
        return data.toString()
        
