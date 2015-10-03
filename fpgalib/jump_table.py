# Author: Daniel Sank
# Created: July 2013

import numpy as np
from fpgalib.util import littleEndian
from fpgalib import fpga

IDLE_NUM_BITS = 15
IDLE_MIN_CYCLES = 0
IDLE_MAX_CYCLES = (2 ** IDLE_NUM_BITS) - 1


class JumpEntry(object):
    """A single entry in the jump table.

    Attributes:
        from_addr(int): SRAM cell at which this entry fires.
        to_addr(int): SRAM cell to which we go after executing this
            entry.
        operation (Operation): Operation performed by this entry.
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
        """Get a byte array representing this entry.

        :return: ndarray(dtype='u1') of bytes for this entry.
        :rtype: np.ndarray
        """
        data = np.zeros(8, dtype='u1')
        data[0:3] = littleEndian(self.from_addr, 3)
        data[3:6] = littleEndian(self.to_addr, 3)
        data[6:8] = self.operation.as_bytes()
        return data


# Operations (ie op codes)

class Operation(object):
    """A Super class for all possible jump table operations"""
    NAME = 'INVALID'  # subclasses must override

    def __str__(self):
        raise NotImplementedError()

    def as_bytes(self):
        """Get an array of bytes representing this operation.

        Each operation is represented by two bytes in memory (little
        endian). This function returns an array corresponding to those bytes.

        Returns:
            2 element ndarray with dtype 'u1' in little endian order.
        """
        raise NotImplementedError()


class IDLE(Operation):
    """Idle operation

    Attributes:
        cycles (int): Number of FPGA cycles to idle.
    """
    NAME = "IDLE"

    def __init__(self, cycles):
        self.cycles = cycles

    def __str__(self):
        return "%s %d cycles" % (self.NAME, self.cycles)

    def as_bytes(self):
        """Get bytes for an IDLE.

        The op code is
            dddddddd ddddddd0
        where d[14..0] is the number of FPGA cycles to idle.
        """
        if not (IDLE_MIN_CYCLES <= self.cycles <= IDLE_MAX_CYCLES):
            raise ValueError(
                "IDLE num cycles must fit in {} bits".format(
                    IDLE_NUM_BITS
                )
            )
        return littleEndian(self.cycles << 1, 2)


class CHECK(Operation):
    """Check daisychain value.

    Attributes:
        which_daisy_bit (int): Which daisy bit to check.
            Need to explain how the numbering works.
        jump_index (int): Index of jump entry to activte after the check.
        bit_state (bool): Selects whether to fire on 0 or 1.
        Need to explain more.

    This operation has not been implemented/tested.
    """
    NAME = "CHECK"

    def __init__(self, which_daisy_bit, bit_state, next_jump_index):
        self.which_daisy_bit = which_daisy_bit
        self.jump_index = next_jump_index
        self.bit_state = bool(bit_state)
        raise NotImplementedError('CHECK is not yet implemented')

    def __str__(self):
        raise NotImplementedError()

    def as_bytes(self):
        """Get bytes for a CHECK

        The op code is
            xxjjjjjj iiiin001
        where
            jjjjjj jump index to set when check is True
            iiii specifies which daisychain bit to check
            n selects whether we check for bit ON or OFF
        """
        jump_idx = self.jump_index << 8
        which_daisy_bit = self.which_daisy_bit << 4
        bit_state = int(self.bit_state) << 3
        op = 1
        val = jump_idx + which_daisy_bit + bit_state + op
        return littleEndian(val, 2)


class JUMP(Operation):
    """Jump to new SRAM address.

    Attributes:
        jump_index (int): Index of jump table entry to activate after
        this one.
    """
    NAME = "JUMP"

    def __init__(self, next_jump_index):
        self.jump_index = next_jump_index

    def __str__(self):
        return '\n'.join([self.NAME, "Next jump index: %d" % self.jump_index])

    def as_bytes(self):
        """Get bytes for a JUMP

        The op code is
            xxjjjjjj xxxx1101
        where
            jjjjjj is the jump index to set after the jump.
        """
        # binary 1101 = decimal 13
        val = (self.jump_index << 8) + 13
        return littleEndian(val, 2)


class NOP(Operation):
    """Do nothing."""
    NAME = "NOP"

    def __str__(self):
        return self.NAME

    def as_bytes(self):
        """Get bytes for a NOP.

        The op code is xxxxxxxx xxxx0101
        """
        return littleEndian(5, 2)


class CYCLE(Operation):
    """Cycle back to another SRAM address.

    Attributes:
    jump_index (int): Index of jump table entry to activate after firing
        this one.
    counter (int): Which counter to increment at each cycle.
    """
    NAME = "CYCLE"

    def __init__(self, counter, next_jump_index):
        """Initialize a cycle opcode.

        :param int counter: which counter to use (0-indexed)
        :param int next_jump_index: JT entry to jump to
        """
        self.jump_index = next_jump_index
        self.counter = counter

    def __str__(self):
        return "{}: counter={}, JT index={}".format(
            self.NAME, self.counter, self.jump_index
        )

    def as_bytes(self):
        """Get bytes for a CYCLE.

        The op code is
            xxjjjjjj xxccx011
        where
            jjjjjj is the jump index to set if the cycle is not done.
            cc is which counter to increment.
        """
        jump_index = self.jump_index << 8
        counter = self.counter << 4
        op = 3
        return littleEndian(jump_index + counter + op, 2)


class END(Operation):
    NAME = "END"

    def __str__(self):
        return self.NAME

    def as_bytes(self):
        """Get bytes for an END.

        The op code is
            xxxxxxxx xxxxx111
        """
        return littleEndian(7, 2)


class JumpTable(object):
    """A jump table.

    This is a very low level wrapper around the actual FPGA data
    structure. The main purpose of this class is to serialize the jump
    table data for writing to the board.


    Attributes:
        counters (list of int): counters[i] is the count value for the
            ith counter.
        start_addr (int): SRAM address at which to start sequence.
        jumps (list of JumpEntry): Ordered list of jump table entries.

    TODO: make self.jumps a property with some checking on type and
        number.
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
        self.counters = self._initialize_counters(counters=counters)
        self.start_addr = start_addr
        self.jumps = jumps

    @classmethod
    def _initialize_counters(cls, counters=None):
        if counters is None:
            c = [0, 0, 0, 0]
        elif len(counters) > cls.NUM_COUNTERS:
            raise ValueError("Cannot have more than 4 counters.")
        else:
            if any([x > cls.COUNT_MAX for x in counters]):
                raise ValueError(
                    "Counter values must fit in {} bits.".format(
                        cls.COUNTER_BITS
                    )
                )
            c = list(counters)
            while len(c) < cls.NUM_COUNTERS:
                c.append(0)
        return c

    def __str__(self):
        counter = '\n'.join(
            "Counter {}: {}".format(
                i, c
            ) for i, c in enumerate(self.counters)
        )
        start_addr = 'Start address: %d' % self.start_addr
        jump = '\n'.join(
            "-JUMP ENTRY {}-\n{}".format(
                i, str(jump)
            ) for i, jump in enumerate(self.jumps)
        )
        return '\n'.join([counter, start_addr, jump])

    def toString(self):
        """Serialize jump table to a byte string for the FPGA"""
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

    This function applies the same offsets as the fpga server, meaning that:

    If stopAddr > 6:
    The sequence should show a pulse of 8ns length, followed by a gap of 8ns,
    and then another 4ns pulse. Since the system idles over the cell one before
    the cell pointed to by the END command, the idle state should be all zero.

    If stopAddr == 6
    The system will idle inside the final 4ns pulse, meaning the idle values
    are high, not zero. The second pulse will not appear to have an end because
    of this.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[4:12] = 0.2
    waveform[20:24] = 0.4

    jumpEntries = []

    # End execution
    op = END()

    fromAddr = stopAddr + build_cls.JT_END_ADDR_OFFSET
    toAddr = 0  # Should be 0 for END and other ops w/o toAddrs
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def test_sine(length, build_number=15):
    """ Return SRAM and a JT for a sine wave of length ns.

    Note that the sequence will be four ns longer than specified,
    with the last four being zeros to be idled over. Also, it will be rounded
    down to the nearest 4 ns. Length < 12 probably won't work.

    :param int length: length of sine wave, in ns.
    :param int build_number: build number for which to use offsets
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    length = (length // 4) * 4
    waveform = 0.4*np.sin(2*np.pi/256*8*np.arange(length + 4))
    waveform[-4:] *= 0
    jump_entries = []

    # End execution
    op = END()
    from_addr = length // 4 + build_cls.JT_END_ADDR_OFFSET
    to_addr = 0
    jump_entries.append(JumpEntry(from_addr, to_addr, op))

    table = JumpTable(0)
    table.jumps = jump_entries

    return waveform, table


def testIdle(cycles, build_number=15):
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

    :param int cycles: idle for this many clock cycles.
    :param int build_number: build number for which to use offsets
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[24:28] = 0.7
    waveform[44:48] = 0.4

    jumpEntries = []

    # idle on sram pulse
    op = IDLE(cycles + build_cls.JT_IDLE_OFFSET)
    fromAddr = 28//4 + build_cls.JT_FROM_ADDR_OFFSET
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    # End execution
    op = END()
    fromAddr = 52//4 + build_cls.JT_END_ADDR_OFFSET
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testJump(build_number):
    """Test jump function
    
    The SRAM block we use to store data
    ns   || 0         10        20        30        40        50        60
         || 0123456789012345678901234567890123456789012345678901234567890123
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10 |11 |12 |13 |14 |15 |
    data || ________________________----________________--------____________
    table||                             ^               ^                     ^
                                        Jump            Arrive                End

    :param int build_number: build number for which to use offsets
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[24:28] = 0.8
    waveform[44:52] = 0.8

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(2)
    fromAddr = 28//4 + build_cls.JT_FROM_ADDR_OFFSET
    toAddr = 44//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4 + build_cls.JT_END_ADDR_OFFSET
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testJumpBack(build_number=15):
    """Test jump function

    The SRAM block we use to store data
    ns   || 0         10        20        30        40
         || 012345678901234567890123456789012345678901234
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10
    data ||                        ----____^^^^
    table||            ^                   ^              ^
                       Arrive              Jump           End

    :param int build_number: build number for which to use offsets
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[24:28] = 0.4
    waveform[28:32] = -0.4
    waveform[32:36] = 0.8

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(2)
    fromAddr = 32//4 + build_cls.JT_FROM_ADDR_OFFSET
    toAddr = 12//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4 + build_cls.JT_END_ADDR_OFFSET
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testJumpBackLoop(build_number=15):
    """Test jump function

    The SRAM block we use to store data
    ns   || 0         10        20        30        40
         || 012345678901234567890123456789012345678901234
    cell || 0  |1  |2  |3  |4  |5  |6  |7  |8  |9  |10
    data ||                        ----____^^^^
    table||            ^                   ^
                       Arrive              Jump

    :param int build_number: build number for which to use offsets
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[24:28] = 0.4
    waveform[28:32] = -0.4
    waveform[32:36] = 0.8

    jumpEntries = []

    # Jump at 6th SRAM cell
    op = JUMP(1)
    fromAddr = 32//4 + build_cls.JT_FROM_ADDR_OFFSET
    toAddr = 12//4
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    op = END()
    fromAddr = 256//4 + build_cls.JT_END_ADDR_OFFSET
    toAddr = 0
    jumpEntries.append(JumpEntry(fromAddr, toAddr, op))

    table = JumpTable(0)
    table.jumps = jumpEntries

    return waveform, table


def testCycle(num_cycles, build_number=15):
    """Test cycle function

    The SRAM block we use to store data
    ns   || 10        20    || 40        50        60 || 70        80
         || 012345678901234 || 0123456789012345678901 || 01234567890123
    cell ||  |3  |4  |5  |6 || 10 |11 |12 |13 |14 |15 ||  |18 |19 |20 |
    data ||  -------------  ||         _--_           || ----------
         ||                 ||      __/ 0.3\__        ||
         ||   level=0.8     ||   __/          \__     ||  level=0.5
         ||                 || _/                \_   ||
    table||               ^                        ^               ^
                          END                      CYCLE to 40     JUMP to 100

    ns   || 100       110       120
         || 012345678901234567890123
    cell || 25 |26 |27 |28 |29 |30 |
    data ||         _--_
         ||      __/ 0.7\__
         ||   __/          \__
         || _/                \_
    table||                     ^
                                JUMP to 4

    What you should see:

    The first jump entry is a cycle with from_addr at cell 15 so we just play
    data until then. Thereofre, you'll see ten ns of zeros, then output=0.8 from
    10 ns to 24 ns, then zeros until 40 ns, then a triangle up to output=0.3
    starting at 40 ns and ending at 60 ns. Then we hit the cycle and go back to
    40 ns, so we see the triangle a second time. After the triangle we see zeros
    for 10 ns. Then we see 10 ns of contant output=0.5. Then we see a triangle
    from output=0 to output=0.7 and back over 20 ns, and then we finish on
    output=0.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[10:24] = 0.8
    waveform[40:50] = np.linspace(0, 0.3, 10)
    waveform[50:60] = np.linspace(0.3, 0, 10)
    waveform[70:80] = 0.5
    waveform[100:110] = np.linspace(1.0, 0.7, 10)
    waveform[110:120] = np.linspace(0.7, 1.0, 10)

    jumpEntries = [
        # cycle: go back to 40, JT index 1, until count passed
        # (i.e. repeat 40-60)
        JumpEntry(60//4 + build_cls.JT_FROM_ADDR_OFFSET,
                  40//4,
                  CYCLE(0, 1)),
        # jump, just for fun
        JumpEntry(80//4 + build_cls.JT_FROM_ADDR_OFFSET,
                  100//4,
                  JUMP(3)),
        # back to beginning to finish
        JumpEntry(120//4 + build_cls.JT_FROM_ADDR_OFFSET,
                  0,
                  JUMP(4)),
        JumpEntry(24//4 + build_cls.JT_END_ADDR_OFFSET,
                  0,
                  END())
    ]
    # Note that we can't move the first jump any earlier than 72//4 = 18,
    # because 56//4 = 14 and fromAddrs must be separated by at least 4.

    table = JumpTable(
        0,
        counters=[num_cycles, num_cycles, num_cycles, num_cycles]
    )
    table.jumps = jumpEntries
    return waveform, table
