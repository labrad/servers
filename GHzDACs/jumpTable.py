# Author: Daniel Sank
# Created: July 2013

import numpy as np
from util import littleEndian

JUMP_INDEX_MIN = 0
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
    """ A single entry in the jump table.

    * Every from address has 2 subtracted to account for FPGA timing offsets.
    * The END entry has an additional 1 subtracted.
    * IDLE has one clock cycle subtracted from idle length as well.

    A note about from addresses:

    We subtract 2 from the from_addr passed into the JumpEntry. The reason for
    this is that by convention we set the end address of an algorithm to the
    length of the sequence. That is, if the SRAM is length 256 ns, then we set
    the end address to 256//4 == 64. However, if we want to idle over the last
    4 ns/jump after the last 4 ns/whatever, then we need to notice that those
    4ns are from 252 - 255, i.e. address 63. So we set the from_address to 62,
    because the actual fromAddress must be one less than the address you want,
    due to FPGA offsets, per John's documentation. (In the case of END, it's
    two less, and that's handled as well.)
    """

    def __init__(self, from_addr, to_addr, operation):
        """ Create a single jump table entry.

        :param int from_addr: the from address
        :param int to_addr: the to address (should be 0 if not used)
        :param Operation operation: the operation
        """
        if abs(from_addr - to_addr) - 1 == 0:
            raise ValueError(
                "from_addr: {} and to_addr: {} are too close".format(
                    from_addr, to_addr)
            )
        self._to_addr = 0
        self._from_addr = 0
        self.from_addr = from_addr - 2  # account for offsets, see docstring
        self.to_addr = to_addr
        self.operation = operation

        if self.operation.NAME == 'END':
            self.from_addr -= 1  # account for additional END offset

    @property
    def to_addr(self):
        return self._to_addr

    @to_addr.setter
    def to_addr(self, addr):
        if SRAM_ADDR_MIN <= addr <= SRAM_ADDR_MAX:
            self._to_addr = addr
        else:
            raise ValueError("Must have {0} <= toAddress <= {1}, not {2}".format(SRAM_ADDR_MIN, SRAM_ADDR_MAX, addr))

    @property
    def from_addr(self):
        return self._from_addr

    @from_addr.setter
    def from_addr(self, addr):
        if SRAM_ADDR_MIN <= addr <= SRAM_ADDR_MAX:
            self._from_addr = addr
        else:
            raise ValueError("Must have {0} <= fromAddr <= {1}, not {2}".format(SRAM_ADDR_MIN, SRAM_ADDR_MAX, addr))

    def __str__(self):
        f_str = "from_addr: %d" % self.from_addr
        t_str = "to_addr: %d" % self.to_addr
        op_str = str(self.operation)
        return '\n'.join([f_str, t_str, op_str])

    def as_bytes(self):
        data = np.zeros(8, dtype='<u1')
        data[0:3] = littleEndian(self.from_addr, 3)
        data[3:6] = littleEndian(self.to_addr, 3)
        data[6:8] = littleEndian(self.operation.as_bytes(), 2)
        return data


# Operations (ie op codes)

class Operation(object):
    """A Super class for all possible jump table operations"""
    NAME = 'INVALID'  # subclasses must override

    @property
    def jump_index(self):
        return self._jump_index

    @jump_index.setter
    def jump_index(self, idx):
        if JUMP_INDEX_MIN <= idx <= JUMP_INDEX_MAX:
            self._jump_index = idx
        else:
            raise ValueError("Must have {0} < jump index < {1}, not {2}".format(JUMP_INDEX_MIN, JUMP_INDEX_MAX, idx))

    def __str__(self):
        raise NotImplementedError()

    def as_bytes(self):
        """Override in subclass"""
        raise NotImplementedError()


class IDLE(Operation):
    NAME = "IDLE"

    def __init__(self, cycles):
        self._cycles = 0
        self.cycles = cycles - 1  # account for FPGA firmware timing offset

    @property
    def cycles(self):
        return self._cycles

    @cycles.setter
    def cycles(self, cycles):
        if IDLE_MIN_CYCLES < cycles < IDLE_MAX_CYCLES:
            self._cycles = cycles
        else:
            raise ValueError(
                'Number of idle cycles must satisfy: {0} < cycles < {1}, '
                'not {2}'.format(IDLE_MIN_CYCLES, IDLE_MAX_CYCLES, cycles)
            )

    def __str__(self):
        return "%s %d cycles" % (self.NAME, self.cycles)

    def as_bytes(self):
        return self._cycles << 1


class CHECK(Operation):
    NAME = "CHECK"

    def __init__(self, which_daisy_bit, bit_state, next_jump_index):
        self._which_daisy_bit = 0
        self.which_daisy_bit = which_daisy_bit
        self.jump_index = next_jump_index
        self.bitOnOff = bool(bit_state)
        raise NotImplementedError('CHECK is not yet implemented')

    @property
    def which_daisy_bit(self):
        return self._which_daisy_bit

    @which_daisy_bit.setter
    def which_daisy_bit(self, which_bit):
        if DAISY_VALUE_MIN < which_bit < DAISY_VALUE_MAX:
            self._which_daisy_bit = which_bit
        else:
            raise ValueError("Must have %s < daisy whichDaisyBit < %s" % (DAISY_VALUE_MIN, DAISY_VALUE_MAX))

    def as_bytes(self):
        # Op code is 001, so shift 4 bits and add 1
        return (self.jump_index << 8) + (self.which_daisy_bit << 4) + (int(self.bitOnOff) << 3) + 1


class JUMP(Operation):
    NAME = "JUMP"

    def __init__(self, next_jump_index):
        self.jump_index = next_jump_index

    def __str__(self):
        return '\n'.join([self.NAME, "Next jump index: %d" % self.jump_index])

    def as_bytes(self):
        # Op code is 1101 = 13
        return (self.jump_index << 8) + 13


class NOP(Operation):
    NAME = "NOP"

    def __str__(self):
        return self.NAME

    def as_bytes(self):
        return 0x0005


class CYCLE(Operation):
    NAME = "CYCLE"

    def __init__(self, counter, next_jump_index):
        self.jump_index = next_jump_index
        self._whichCounter = 0
        self.which_counter = counter

    @property
    def which_counter(self):
        return self._whichCounter

    @which_counter.setter
    def which_counter(self, which_counter):
        if 0 <= which_counter < NUM_COUNTERS:
            self._whichCounter = which_counter
        else:
            raise RuntimeError("Must have %s < which_counter < %s" % (0, NUM_COUNTERS))

    def as_bytes(self):
        return (self.jump_index << 8) + (self.which_counter << 4) + 3


class END(Operation):
    NAME = "END"

    def __str__(self):
        return self.NAME

    def as_bytes(self):
        return 7


class JumpTable(object):
    """
    The entire jump table.
    
    This is a very low level wrapper around the actual FPGA data structure
    
    TODO: make self.jumps a property with some checking on type and number
    """
    PACKET_LEN = 528
    COUNT_MAX = 2 ** 32 - 1  # 32 bit register for counters

    def __init__(self, start_addr=None, jumps=None, counters=None):
        """

        :param start_addr: start address
        :param list[JumpEntry] jumps: the jump table entries
        :param list[int] counters: the counter values
        """
        self._startAddr = 0
        if counters is None:
            self._counters = [0, 0, 0, 0]
        else:
            self._counters = list(counters)[0:4]
        self.start_addr = start_addr
        self.jumps = jumps

    @property
    def start_addr(self):
        return self._startAddr

    @start_addr.setter
    def start_addr(self, addr):
        if SRAM_ADDR_MIN <= addr <= SRAM_ADDR_MAX:
            self._startAddr = addr
        else:
            raise ValueError("Must have {0} <= start addr <= {1}, not {2}".format(SRAM_ADDR_MIN, SRAM_ADDR_MAX, addr))

    # TODO: error check counter values

    def __str__(self):
        counter = '\n'.join("Counter %d: %d" % (i, c) for i, c in enumerate(self._counters))
        start_addr = 'Start address: %d' % self.start_addr
        jump = '\n'.join("-JUMP ENTRY %d-\n%s" % (i, str(jump)) for i, jump in enumerate(self.jumps))
        return '\n'.join([counter, start_addr, jump])

    def toString(self):
        """Write a byte string for the FPGA"""
        data = np.zeros(self.PACKET_LEN, dtype='<u1')
        # Set counter maxima. Each one is 4 bytes
        for i, c in enumerate(self._counters):
            data[i * 4:(i + 1) * 4] = littleEndian(c, 4)
        # Set start address
        data[16:19] = littleEndian(self.start_addr, 3)
        data[19:22] = littleEndian(self.start_addr, 3)
        # Start op code
        data[22] = 5
        data[23] = 0
        for i, jump in enumerate(self.jumps):
            data[24 + (i * 8):24 + ((i + 1) * 8)] = jump.as_bytes()
        return data.tostring()

    def pretty_string(self):
        s = ''
        data = self.toString()
        i = 0
        # counters
        for j in range(4):
            s += '{0:02x} {1:02x} {2:02x} {3:02x}'.format(*[ord(x) for x in data[i:i+4]])
            i += 4
            s += '\n'
        # table commands
        for j in range((528-16)//8):
            s += '{0:02x} {1:02x} {2:02x}  '.format(*[ord(x) for x in data[i:i+3]])
            i += 3
            s += '{0:02x} {1:02x} {2:02x}  '.format(*[ord(x) for x in data[i:i+3]])
            i += 3
            s += '{0:02x} {1:02x}  '.format(*[ord(x) for x in data[i:i+2]])
            i += 2
            s += '\n'
        # print i
        # print len(data)
        assert(i == len(data))
        return s


# Simple functions
def jt_run_sram(start_addr, end_addr, loop=False):
    """
    Simple JT to run the SRAM
    :param int start_addr: SRAM start address
    :param int end_addr: SRAM end address
    :param bool loop: loop?
    :return: jump table object
    :rtype: JumpTable
    """
    jump_entries = []
    if end_addr < 4:
        raise ValueError("Cannot have sequence shorter than fromAddr == 4")
    from_addr = end_addr
    if not loop:
        jump_entries.append(JumpEntry(from_addr, 0, END()))
    else:
        jump_entries.append(JumpEntry(from_addr, start_addr, JUMP(1)))
    return JumpTable(start_addr, jump_entries)


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
    waveform[40:120] = 0.2
    waveform[200:220] = 0.4
    # waveform[44:48] = 0.4
    # waveform[48:60] = 0.3

    jumpEntries = []

    # End execution
    op = END()
    fromAddr = stopAddr
    toAddr = 0              # Should be 0 for END and other ops w/o toAddrs
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def test_sine(length):
    """ Return SRAM and a JT for a sine wave of length ns.

    Note that the sequence will be four ns longer than specified,
    with the last four being zeros to be idled over. Also, it will be rounded
    down to the nearest 4 ns. Length < 12 probably won't work.

    :param int length: length of sine wave, in ns.
    :return:
    """
    length = (length // 4) * 4
    waveform = 0.4*np.sin(2*np.pi/256*8*np.arange(length + 4))
    waveform[-4:] *= 0
    jump_entries = []

    # End execution
    op = END()
    from_addr = length // 4
    to_addr = 0
    jump_entries.append(JumpEntry(from_addr, to_addr, op))

    table = JumpTable(0)
    table.jumps = jump_entries

    return waveform, table


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
    table||                         IDLE                        END
    
    The fromAddr for the IDLE command is set to cell number 6. Therefore, you
    should see a pulse of length (1+cycles)*4ns, followed by 16ns of zeros,
    followed by a 4ns pulse. The system should then idle with zeros.
    """
    waveform = np.zeros(256)
    waveform[24:28] = 0.7
    waveform[44:48] = 0.4

    jumpEntries = []

    op = IDLE(cycles)
    fromAddr = 28//4  # idle on sram pulse
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    # End execution
    op = END()
    fromAddr = 52//4
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testJump():
    """Test jump function
    
    The SRAM block we use to store data
    ns   || 0         10        20        30        40        50        60
         || 0123456789012345678901234567890123456789012345678901234567890123
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10 |11 |12 |13 |14 |15 |
    data || ________________________----________________--------____________
    table||                             ^               ^                     ^
                                        Jump            Arrive                End
    """
    waveform = np.zeros(256)
    waveform[24:28] = 0.8
    waveform[44:52] = 0.8

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(2)
    fromAddr = 28//4
    toAddr = 44//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testJumpBack():
    """Test jump function

    The SRAM block we use to store data
    ns   || 0         10        20        30        40
         || 012345678901234567890123456789012345678901234
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10
    data ||                        ----____^^^^
    table||            ^                   ^              ^
                       Arrive              Jump           End
    """
    waveform = np.zeros(256)
    waveform[24:28] = 0.4
    waveform[28:32] = -0.4
    waveform[32:36] = 0.8

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(2)
    fromAddr = 32//4
    toAddr = 12//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testJumpBackLoop():
    """Test jump function

    The SRAM block we use to store data
    ns   || 0         10        20        30        40
         || 012345678901234567890123456789012345678901234
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10
    data ||                        ----____^^^^
    table||            ^                   ^
                       Arrive              Jump
    """
    waveform = np.zeros(256)
    waveform[24:28] = 0.4
    waveform[28:32] = -0.4
    waveform[32:36] = 0.8

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(1)
    fromAddr = 32//4
    toAddr = 12//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testCycle(num_cycles):
    waveform = np.zeros(256)
    waveform[10:20] = 0.8
    waveform[40:50] = np.linspace(0, 0.3, 10)
    waveform[50:60] = np.linspace(0.3, 0, 10)
    waveform[100:110] = np.linspace(1.0, 0.7, 10)
    waveform[110:120] = np.linspace(0.7, 1.0, 10)

    jumpEntries = [
        JumpEntry(56//4, 40//4, CYCLE(0, 1)),  # cycle: go back to 40, JT index 1, until count passed (i.e. repeat 40-60)
        JumpEntry(72//4, 100//4, JUMP(3)),     # jump, just for fun
        JumpEntry(120//4, 0, JUMP(4)),         # back to beginning to finish
        JumpEntry(20//4, 0, END())
    ]
    # note that we can't move the first jump any earlier than 72//4 = 18, because 56//4 = 14 and fromAddrs must be
    # separated by at least 4

    table = JumpTable(0, counters=[num_cycles, num_cycles, num_cycles, num_cycles])
    table.jumps = jumpEntries
    return waveform, table