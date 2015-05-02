# Author: Daniel Sank
# Created: July 2013

import numpy as np
from util import littleEndian

IDLE_NUM_BITS = 15
IDLE_MIN_CYCLES = 0
IDLE_MAX_CYCLES = (2 ** IDLE_NUM_BITS) - 1


class JumpEntry(object):
    """ A single entry in the jump table.

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

        self.from_addr = from_addr
        self.to_addr = to_addr
        self.operation = operation

    def __str__(self):
        f_str = "from_addr: %d" % self.from_addr
        t_str = "to_addr: %d" % self.to_addr
        op_str = str(self.operation)
        return '\n'.join([f_str, t_str, op_str])

    def as_bytes(self):
        """ Get the byte code for this JT entry.

        :return: ndarray(dtype='u1') of bytes for this entry.
        :rtype: np.ndarray
        """
        data = np.zeros(8, dtype='u1')
        data[0:3] = littleEndian(self.from_addr, 3)
        data[3:6] = littleEndian(self.to_addr, 3)
        data[6:8] = littleEndian(self.operation.as_int(), 2)
        return data


# Operations (ie op codes)

class Operation(object):
    """A Super class for all possible jump table operations"""
    NAME = 'INVALID'  # subclasses must override

    def __str__(self):
        raise NotImplementedError()

    def as_int(self):
        """ Return the integer equivalent to the byte code for operation.

        It represents two (little endian) bytes. It can be translated to bytes
        with ``util.littleEndian(my_operation.as_int(), 2)``.
        """
        raise NotImplementedError()


class IDLE(Operation):
    NAME = "IDLE"

    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "%s %d cycles" % (self.NAME, self.cycles)

    def as_int(self):
        if not (IDLE_MIN_CYCLES <= self.cycles <= IDLE_MAX_CYCLES):
            raise ValueError("IDLE num cycles must fit in {} bits".format(
                IDLE_NUM_BITS
            ))
        return self.cycles << 1


class CHECK(Operation):
    NAME = "CHECK"

    def __init__(self, which_daisy_bit, bit_state, next_jump_index):
        self.which_daisy_bit = which_daisy_bit
        self.jump_index = next_jump_index
        self.bit_state = bool(bit_state)
        raise NotImplementedError('CHECK is not yet implemented')

    def as_int(self):
        # Op code is 001, so shift 4 bits and add 1
        return (self.jump_index << 8) + (self.which_daisy_bit << 4) + (int(self.bit_state) << 3) + 1


class JUMP(Operation):
    NAME = "JUMP"

    def __init__(self, next_jump_index):
        self.jump_index = next_jump_index

    def __str__(self):
        return '\n'.join([self.NAME, "Next jump index: %d" % self.jump_index])

    def as_int(self):
        # Op code is 1101 = 13
        return (self.jump_index << 8) + 13


class NOP(Operation):
    NAME = "NOP"

    def __str__(self):
        return self.NAME

    def as_int(self):
        return 5


class CYCLE(Operation):
    NAME = "CYCLE"

    def __init__(self, counter, next_jump_index):
        """ Create a cycle opcode.

        :param int counter: which counter to use (0-indexed)
        :param int next_jump_index: JT entry to jump to
        """
        self.jump_index = next_jump_index
        self.counter = counter

    def as_int(self):
        return (self.jump_index << 8) + (self.counter << 4) + 3

    def __str__(self):
        return "{}: counter={}, JT index={}".format(
            self.NAME, self.counter, self.jump_index
        )


class END(Operation):
    NAME = "END"

    def __str__(self):
        return self.NAME

    def as_int(self):
        return 7


class JumpTable(object):
    """
    The entire jump table.
    
    This is a very low level wrapper around the actual FPGA data structure
    
    TODO: make self.jumps a property with some checking on type and number
    """
    PACKET_LEN = 528
    COUNTER_BITS = 32  # 32 bit register for counters
    COUNT_MAX = 2**COUNTER_BITS - 1
    NUM_COUNTERS = 4

    def __init__(self, start_addr=None, jumps=None, counters=None):
        """

        :param start_addr: start address
        :param list[JumpEntry] jumps: the jump table entries
        :param list[int] counters: the counter values
        """
        self._startAddr = 0
        if counters is None:
            self.counters = [0, 0, 0, 0]
        elif len(counters) > self.NUM_COUNTERS:
            raise ValueError("Cannot have more than 4 counters.")
        else:
            if any([x > self.COUNT_MAX for x in counters]):
                raise ValueError("Counter values must fit in {} bits.".format(
                    self.COUNTER_BITS
                ))
            self.counters = list(counters)
            while len(self.counters) < self.NUM_COUNTERS:
                self.counters.append(0)
        self.start_addr = start_addr
        self.jumps = jumps

    def __str__(self):
        counter = '\n'.join("Counter %d: %d" % (i, c) for i, c in enumerate(self.counters))
        start_addr = 'Start address: %d' % self.start_addr
        jump = '\n'.join("-JUMP ENTRY %d-\n%s" % (i, str(jump)) for i, jump in enumerate(self.jumps))
        return '\n'.join([counter, start_addr, jump])

    def toString(self):
        """Write a byte string for the FPGA"""
        data = np.zeros(self.PACKET_LEN, dtype='<u1')
        # Set counter values. Each one is 4 bytes
        for i, c in enumerate(self.counters):
            data[i * 4:(i + 1) * 4] = littleEndian(c, 4)
        # Set start address
        data[16:19] = littleEndian(self.start_addr, 3)
        data[19:22] = littleEndian(self.start_addr, 3)
        # Start op code
        data[22] = 5
        data[23] = 0
        for i, jump in enumerate(self.jumps):
            ofs = 24 + i * 8
            data[ofs:ofs+8] = jump.as_bytes()
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


# TEST FUNCTIONS

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
    from_addr = length // 4 - 3
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
    fromAddr = 28//4 - 2
    toAddr = 44//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4 - 3
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
    fromAddr = 32//4 - 2
    toAddr = 12//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4 - 3
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
    fromAddr = 32//4 - 2
    toAddr = 12//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4 - 3
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