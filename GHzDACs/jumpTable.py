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
    def __init__(self, fromAddr, toAddr, opCode):
        self.fromAddr = fromAddr
        self.toAddr = toAddr
        self.operation = operation

class Operation(object):
    def getJumpIndex(self):
        return self._jumpIndex
    def setJumpIndex(self, idx):
        if <idx<:
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
    
    def setJumpIndex(self, idx):
        raise RuntimeError('IDLE does not support jump table indexing')
    
    def getIdleCycles(self):
        return self._cycles
    def setIdleCycles(self, cycles):
        if cycles<IDLE_MAX_CYCLES and cycles > IDLE_MIN_CYCLES:
            self._cycles = cycles
        else:
            raise RuntimeError('must have %s<IDLE cycles<%s'%(IDLE_MIN_CYCLES,IDLE_MAX_CYCLES))
    cycles = property(getIdleCycles, setIdleCycles)
    
    def asBytes(self):
        return self._cycles<<1
        
class CHECK(Operation):
    def __init__(self, daisyValue, nextJumpIndex):
        self._daisyValue = daisyValue
        self._jumpIndex = nextJumpIndex

    def getCheckValue(self):
        return self._daisyValue
    def setCheckValue(self, value):
        if value<DAISY_VALUE_MAX and value>DAISY_VALUE_MIN:
            self._daisyValue = value
        else:
            raise RuntimeError('Must have %s<daisy check value<%s'%(DAISY_CHECK_MIN, DAISY_CHECK_MAX))
    daisyValue = property(getCheckValue, setCheckValue)
    
    def asBytes(self):
        pass
   
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
        
class Block(object):
    """A single block of SRAM to be executed without any jumps"""