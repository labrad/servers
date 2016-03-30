# Author: Daniel Sank
# Created: July 2013

import numpy as np
from fpgalib.util import littleEndian

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

        # TODO: Why is this -1 hard coded?
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
             Note: jump_table gets an extra NOP start entry at run time in
            self.toString, so first user entry is index 1.
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
            this one. Note: jump_table gets an extra NOP start entry at run time
            in self.toString, so first user entry is index 1.
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
            this one. Note: jump_table gets an extra NOP start entry at run time
            in self.toString, so first user entry is index 1.
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

    # TODO: Move these hardcoded FPGA values
    COUNTER_BITS = 32  # 32 bit register for counters
    COUNT_MAX = 2**COUNTER_BITS - 1
    NUM_COUNTERS = 4

    def __init__(self, start_addr=None, jumps=None, counters=None,
                 packet_len=528):
        """

        :param start_addr: start address
        :param list[JumpEntry] jumps: the jump table entries
        :param list[int] counters: the counter values
        :param int packet_len: Number of byes in jump table write packet
        """
        self._startAddr = 0
        self.counters = self._initialize_counters(counters=counters)
        self.start_addr = start_addr
        self.jumps = jumps
        self.packet_len = packet_len

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
        data = np.zeros(self.packet_len, dtype='<u1')
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
