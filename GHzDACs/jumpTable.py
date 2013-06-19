#Unit testing
# Check that all idle values actually work, ie can we use all bits?

from util import littleEndian

class Jump(object):
    def __init__(self, fromAddr, toAddr, opCode, index):
        self.fromAddr = fromAddr
        self.toAddr = toAddr
        self.opCode = opCode
        self.index = index

class Operation(object):
    def asBytes(self):
        raise NotImplementedError

class IDLE(Operation):
    MAX_TIME = 

    def __init__(self, time_ns):
        self.time_ns = time_ns
    
    def asBytes():
    
    
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