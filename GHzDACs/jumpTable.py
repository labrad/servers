# Author: Daniel Sank
# Created: July 2013

import numpy as np
from util import littleEndian

JUMP_INDEX_MIN = 1
JUMP_INDEX_MAX = 15
IDLE_MIN_CYCLES = 1
IDLE_MAX_CYCLES = (2 ** 15) - 1
DAISY_VALUE_MIN = 0
DAISY_VALUE_MAX = 15

NUM_COUNTERS = 4

SRAM_ADDR_MIN = 0
SRAM_ADDR_MAX = 8192 - 1  # XXX HACK ALERT! This should be imported from other module or registry!!!

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
            raise RuntimeError("Must have %s <= toAddr <= %s" % (SRAM_ADDR_MIN, SRAM_ADDR_MAX))

    toAddr = property(getToAddr, setToAddr)

    def getFromAddr(self):
        return self._fromAddr

    def setFromAddr(self, addr):
        if SRAM_ADDR_MIN <= addr and addr <= SRAM_ADDR_MAX:
            self._fromAddr = addr
        else:
            raise RuntimeError("Must have %s <= fromAddr <= %s" % (SRAM_ADDR_MIN, SRAM_ADDR_MAX))

    fromAddr = property(getFromAddr, setFromAddr)

    def __str__(self):
        fromAddrStr = "fromAddr: %d" % self.fromAddr
        toAddrStr = "toAddr: %d" % self.toAddr
        opStr = str(self.operation)
        return '\n'.join([fromAddrStr, toAddrStr, opStr])

    def asBytes(self):
        data = np.zeros(8, dtype='<u1')
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
        if JUMP_INDEX_MIN <= idx <= JUMP_INDEX_MAX:
            self._jumpIndex = idx
        else:
            raise RuntimeError("Must have %s < jump index < %s" % (JUMP_INDEX_MIN, JUMP_INDEX_MAX))

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
            raise RuntimeError(
                'Number of idle cycles must satisfy: %s < cycles < %s' % (IDLE_MIN_CYCLES, IDLE_MAX_CYCLES))

    cycles = property(getCycles, setCycles)

    def __str__(self):
        return "%s %d cycles" % (self.NAME, self.cycles)

    def asBytes(self):
        return self._cycles << 1


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
            raise RuntimeError("Must have %s < daisy whichDaisyBit < %s" % (DAISY_VALUE_MIN, DAISY_VALUE_MAX))

    whichDaisyBit = property(getWhichDaisyBit, setWhichDaisyBit)

    def asBytes(self):
        # Op code is 001, so shift 4 bits and add 1
        return (self.jumpIndex << 8) + (self.whichDaisyBit << 4) + (int(self.bitOnOff) << 3) + 1


class JUMP(Operation):
    NAME = "JUMP"

    def __init__(self, nextJumpIndex):
        self.jumpIndex = nextJumpIndex

    def __str__(self):
        return '\n'.join([self.NAME, "Next jump index: %d" % self.jumpIndex])

    def asBytes(self):
        # Op code is 1101 = 13
        return (self.jumpIndex << 8) + 13


class NOP(Operation):
    NAME = "NOP"

    def __str__(self):
        return self.NAME

    def asBytes(self):
        return 0x0005


class CYCLE(Operation):
    NAME = "CYCLE"

    def __init__(self, counter, nextJumpIndex):
        self.jumpIndex = nextJumpIndex
        self._whichCounter = 0
        self.whichCounter = counter

    @property
    def whichCounter(self):
        return self._whichCounter

    @whichCounter.setter
    def whichCounter(self, whichCounter):
        if 0 <= whichCounter < NUM_COUNTERS:
            self._whichCounter = whichCounter
        else:
            raise RuntimeError("Must have %s < whichCounter < %s" % (0, NUM_COUNTERS))

    def asBytes(self):
        return (self.jumpIndex << 8) + (self.whichCounter << 4) + 3


class END(object):
    NAME = "END"

    def __str__(self):
        return self.NAME

    def asBytes(self):
        return 7


class JumpTable(object):
    """
    The entire jump table.
    
    This is a very low level wrapper around the actual FPGA data structure
    
    TODO: make self.jumps a property with some checking on type and number
    """
    PACKET_LEN = 528
    COUNT_MAX = 2 ** 32 - 1  # 32 bit register for counters

    def __init__(self, startAddr=None, jumps=None, counters=None):
        """

        :param startAddr: start address
        :param jumps:
        """
        self._startAddr = 0
        if counters is None:
            self._counters = [0, 0, 0, 0]
        else:
            self._counters = list(counters)[0:4]
        self.startAddr = startAddr
        self.jumps = jumps

    @property
    def startAddr(self):
        return self._startAddr

    @startAddr.setter
    def startAddr(self, addr):
        if SRAM_ADDR_MIN <= addr <= SRAM_ADDR_MAX:
            self._startAddr = addr
        else:
            raise RuntimeError("Must have %s <= start addr <= %s" % (SRAM_ADDR_MIN, SRAM_ADDR_MAX))

    # TODO: error check counter values

    def __str__(self):
        counterStr = '\n'.join("Counter %d: %d" % (i, c) for i, c in enumerate(self._counters))
        startAddrStr = 'Start address: %d' % self.startAddr
        jumpsStr = '\n'.join("-JUMP ENTRY %d-\n%s" % (i, str(jump)) for i, jump in enumerate(self.jumps))
        return '\n'.join([counterStr, startAddrStr, jumpsStr])

    def toString(self):
        """Write a byte string for the FPGA"""
        data = np.zeros(self.PACKET_LEN, dtype='<u1')
        # Set counter maxima. Each one is 4 bytes
        for i, c in enumerate(self._counters):
            data[i * 4:(i + 1) * 4] = littleEndian(c, 4)

        #Set start address
        data[16:19] = littleEndian(self.startAddr, 3)
        data[19:22] = littleEndian(self.startAddr, 3)
        #Start op code
        data[22] = 5
        data[23] = 0
        for i, jump in enumerate(self.jumps):
            data[24 + (i * 8):24 + ((i + 1) * 8)] = jump.asBytes()

        return data.tostring()


# Simple functions

def jtRunSram(startAddr, endAddr, loop=False):
    """
    Simple JT to run the SRAM
    :param int startAddr: SRAM start address
    :param int endAddr: SRAM end address
    :param bool loop: loop?
    :return: jump table object
    :rtype: JumpTable
    """
    jumpEntries = []
    if not loop:
        fromAddr = max(1, endAddr - 2)
        jumpEntries.append(JumpEntry(fromAddr, 0, END()))
    else:
        fromAddr = max(1, endAddr - 1)
        jumpEntries.append(JumpEntry(fromAddr, startAddr, JUMP(1)))
    return JumpTable(startAddr, jumpEntries)


# Unit tests

def testNormal(stopAddr):
    """Test END function
    
    The SRAM block we use to store data
    
    ns  || 0         10        20        30
        || 0123456789012345678901234567890123456789
    cell|| 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |
    data|| ____--------________----____________________
    table                          End
    
    If stopAddr >= 6:
    The sequence should show a pulse of 8ns length, followed by a gap of 8ns,
    and then another 4ns pulse. Since the system idles at the same cell as the
    END command the idle state should be all zero.
    
    If stopAddr == 5
    The system will idle inside the final 4ns pulse, meaning the idle values
    are high, not zero. The second pulse will not appear to have an end because
    of this.1
    
    We observe in this case that if we specify 1 repetition, the system instead
    executes many times. Why? -- this is no longer the case??
    
    If stopAddr==3
    ???
    """
    waveform = np.zeros(256)
    waveform[4:40] = 0.2
    waveform[40:44] = 0.1
    waveform[44:48] = 0.4
    waveform[48:60] = 0.3

    jumpEntries = []

    # End execution
    op = END()
    fromAddr = stopAddr
    toAddr = 0  # Meaningless?
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform * 2**14, table


def testIdle(cycles):
    """Single high sample, followed by idle, followed by single high sample
    
    RETURNS - (sramBlock, table)
     sramBlock - ndarray: numerical SRAM data, not packed as bytes
     table - JumpTable: jump table object
    
    The SRAM block we use to store data
    ns   || 0         10        20        30        40        50        60
         || 0123456789012345678901234567890123456789012345678901234567890123
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10 |11 |12 |13 |14 |15 |
    data || ________________________----________________----________________
    table||                         IDLE                    END
    
    The fromAddr for the IDLE command is set to cell number 6. Therefore, you
    should see a pulse of length (1+cycles)*4ns, followed by 16ns of zeros,
    followed by a 4ns pulse. The system should then idle with zeros.
    """
    waveform = np.zeros(256)
    waveform[24:28] = 0.3
    waveform[44:48] = 0.2

    jumpEntries = []

    # Idle over 6th SRAM cell
    op = IDLE(cycles)
    fromAddr = 6
    toAddr = 0  # Meaningless?
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    # End execution
    op = END()
    fromAddr = 12
    toAddr = 0  # Meaningless?
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform * 2**14, table


def testJump():
    """Test jump function
    
    The SRAM block we use to store data
    ns   || 0         10        20        30        40        50        60
         || 0123456789012345678901234567890123456789012345678901234567890123
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10 |11 |12 |13 |14 |15 |
    data || ________________________----________________----________________
    table||                             ^               ^       ^
                                        Jump            Arrive  End
    """
    waveform = np.zeros(256)
    waveform[24:28] = 0.8
    waveform[44:48] = np.linspace(0.8, 0.5, 4)

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(2)
    fromAddr = 5
    toAddr = 11
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 60
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform * 2**14, table


def testCycle(num_cycles):
    waveform = np.zeros(256)
    waveform[10:20] = 0.8
    waveform[40:50] = np.linspace(0, 0.3, 10)
    waveform[50:60] = np.linspace(0.3, 0, 10)
    waveform[100:110] = np.linspace(1.0, 0.7, 10)
    waveform[110:120] = np.linspace(0.7, 1.0, 10)

    jumpEntries = [
        JumpEntry(56//4, 40//4, CYCLE(0, 1)),  # cycle: go back to 40, JT index 1, until count passed (i.e. repeat 40-60)
        JumpEntry(72//4, 100//4, JUMP(3)),      # jump, just for fun
        JumpEntry(120//4, 0, JUMP(4)),           # back to beginning to finish
        JumpEntry(20//4, 0, END())
    ]
    # note that we can't move the first jump any earlier than 72//4 = 18, because 56//4 = 14 and fromAddrs must be
    # separated by at least 4

    table = JumpTable(0, counters=[num_cycles, num_cycles, num_cycles, num_cycles])
    table.jumps = jumpEntries
    return waveform * 2**14, table