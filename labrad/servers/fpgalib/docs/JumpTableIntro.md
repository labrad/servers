# Introduction
This is a beginner's documentation for the jump table version of the DACs.

*Remember: 8 bits to one byte, 4 bytes to a word, 4 words to a cell, 256 words to a page.*

You can think of the DACs as serving one basic function: you give it a (digital) waveform, and then it plays it out (analog). The pre-jump table version of the DACs had two separate types of commands you could issue: "SRAM write", which defines the waveform (in the SRAM memory); and "memory", which defines the control sequences that play the SRAM. The memory commands were limited to fairly basic operations, such as start, stop, repeat, and wait--it was not possible to have branching code.

The jump table is a replacement for the memory commands that allows for much more complex control. The jump table commands form their own mini-programming language, which contains branching (if-thens) and subroutines (in the form of jumps), as well as the ability to read output from the ADC on the daisy chain.

There are now two pointers that can be manipulated:

* The SRAM pointer determines what the DACs are outputting.
  * This holds a memory address. The DACs play what is at this address, and the pointer gets incremented sequentially.
* The jump table pointer holds the index of the currently active jump table operation.
  * A jump table operation has a few parts:
    * The operation code defines the type of command: e.g. IDLE, CHECK, CYCLE, JUMP, NOP, END
    * The fromAddress is an SRAM address. When the SRAM pointer reaches the fromAddress, this jump table operation is called, and will execute on the _next_ cycle (i.e. the SRAM pointer will be at fromAddress+1 when the jump table operation executes).
    * The toAddress is an SRAM address that is used in the CHECK, CYCLE, and JUMP operations.
    * Note that the fromAddress and the toAddress are given in _cells_, or groups of 4 ns of data. So a fromAddress of 0 corresponds to the SRAM of 0-3 ns, and 1 is 4-7 ns, etc.
  * Jump table operations can manipulate both the SRAM pointer and the jump table pointer.

# Jump Table Operations

Let's make this concrete by enumerating the allowed jump table operations. Each jump table operation is given by a two byte operation code (opcode), as well as two three-byte SRAM addresses, the fromAddress and toAddress. The first byte of the opcode, Byte 0, gives the command and (possibly) arguments to it. The second byte, Byte 1, is commonly devoted to a jump table index. (NB: everything is little endian. "First byte" means least significant byte.) The encoding used below is copied from John's documentation; for example, `xxjjjjjj` means the first two bits `x` are ignored, while the six bits `j` form a single number, the use of which is given in the description. For details of actually defining the jump table, see the section "Jump Table Write" below.

 Name |   Byte 1   |   Byte 0   | Description
------|------------|------------|-------------
IDLE  | `dddddddd` | `ddddddd0` | Wait for n+1 cycles, with n defined by the fifteen bits `d`. SRAM pointer will remain at fromAddress+1.
NOP   | `xxxxxxxx` | `xxxx0101` | Null operation: move both the SRAM pointer and the jump table pointer forward by one.
CHECK | `xxjjjjjj` | `iiiin001` | Query the daisy chain bit at index `iiii`. If it is equal to `n`, move the SRAM pointer to the toAddress and the jump table pointer to the jump table index indicated by `jjjjjj`. If not, move both the SRAM pointer and the jump table pointer forward by one.
JUMP  | `xxjjjjjj` | `xxxx1101` | Move the SRAM pointer to the toAddress, and the jump table pointer to `jjjjjj`.
CYCLE | `xxjjjjjj` | `xxccx011` | Compare the counter* (index given by `cc`) with its countTo parameter (also index `cc`). If false (counter != countTo): increment counter, move SRAM pointer to toAddress, move jump table pointer to `jjjjjj`. If true (counter == countTo): reset counter to 0, move both SRAM pointer and jump table pointer forward by one.
END   | `xxxxxxxx` | `xxxxx111` | End. The SRAM pointer will stop and idle at fromAddress + 2.

*About the counters: there are four counters, and each has a corresponding countTo parameter. The countTo parameters are set at the same time as the jump table (see below).

# Example

We now explain the examples in John's documentation. Note that the startAddress, toAddress, and fromAddress are in hexadecimal.

Notation: the prefix 0x means a number is being expressed in hexadecimal, and 0b is for binary. Hence one byte could be written as 0x1A = 0b00011010 = 26.

Jump Table Index | Opcode | toAddress | fromAddress | Comment
-----------------|--------|-----------|------------|--------
**Normal Sequence** | | | |
0 | `0005` | `000000` | `000000` | First JT entry defines the start address of the SRAM pointer (here, 0). The command is a no-op: 0x05 = `0b00000101` = NOP.
1 | `0007` | `000000` | `000050` | When SRAM reaches the from address (0x50), the sequence will end (0x07 = 0b0111 = END). The SRAM will run to address 0x52 and idle.
**Spin Echo** | | | |
0 | `0005` | `000007` | `000007` | Start at address 7. For the start command, toAddress must be the same as fromAddress.
1 | `0200` | `000000` | `000010` | When SRAM pointer reaches address 0x10 (fromAddress), the IDLE command will be activated: 0x0200 = 0b00000010 00000000 = IDLE of length 256+1. The SRAM pointer will idle at address 0x11 for 257 cycles. Then the SRAM pointer will continue advance and the JT pointer will increase by one, to 2 (the next command)
2 | `0400` | `000000` | `000020` | Same as above: the SRAM pointer will idle at address 0x21 for 512+1 cycles.
3 | `0007` | `000000` | `000050` | End at address 0x52.
 | | | | To work as a spin echo, the SRAM should contain a pi/2 pulse from 0x07 to 0x10, nothing (or a detuning) for 0x11 (which is held during the idle), a pi pulse for 0x12 to 0x20, nothing again for 0x21, and a pi/2 and readout for addresses 0x22 through 0x52. (A true spin echo would have the two delays equal, of course.)
 **All operations** | | | |
 0 | `0005` | `000003` | `000003` | Start at address 3.
 1 | `0129` | `000007` | `000010` | `0x0129 = 0b00000001 00101001` CHECK if daisychain bit 2 (0b0010) is 1. If so, jump SRAM pointer to 7 and JT pointer to 1 (this command again). If not, proceed to next jump table entry.
 2 | `0213` | `000028` | `000030` | `0x0213 = 0b00000010 00010011` CYCLE counter #1, going back to SRAM address 0x28 and JT index 2 (this operation) each time. When cycle completes, advance to next operation.
 3 | `040D` | `000048` | `000040` | `0x040D = 0b00000100 00001101` JUMP SRAM pointer to 0x48 and JT pointer to 4.
 4 | `0004` | `000000` | `000050` | Idle for 2+1 cycles at SRAM address 0x51.
 5 | `0007` | `000000` | `000060` | End at SRAM address 0x62.
 
 The last example does the following:
 
 * Start at 0x03
 * proceed to 0x10 and repeat 0x07 through 0x11 (note the off by one here) until daisy chain bit #2 is 1
 * proceed to 0x30 and repeat 0x28 through 0x30 N times (N is defined elsewhere, see the full protocol below)
 * proceed to 0x40 and then jump to 0x48
 * proceed to 0x51 and idle for 3 cycless 
 * proceed to 0x62 and end.

# The Jump Table Write

This is the specification for defining the jump table. The ethernet packet to write the jump table consists of a 2-byte length header and a 528-byte body. The contents of the packet are detailed below. (The header is generated by the direct ethernet (DE) server and so is not listed here.)

Note that the jump table is defined once, in contrast to the SRAM (see below).

Byte Index (0-indexed) | Name | Description
-----------------------|------|------------
 | | The first 16 bytes define the four counters.
    0 | CountTo0 [0] | Byte 0 (least significant) of counter 0
    1 | CountTo0 [1] | Byte 1 (i.e. bits 8-15.)
    2 | CountTo0 [2] |
    3 | CountTo0 [3] | Last byte of counter 0
  4-7 | CountTo1 [0-3] | Counter 1
 8-11 | CountTo2 [0-3] | Counter 2
12-15 | CountTo3 [0-3] | Counter 3
 | | The remainder of the packet defines the 64 jump table operations, 8 bytes each.
 | | The first JT operation is a special case
16-18 | StartAdr [0-2] | SRAM pointer start address
19-21 | StartAdr [0-2] | must duplicate 16-18
22-23 | StartOpCode [0-1] | The first JT opcode (must=5 for NOP?)
 | | Each normal JT operation is 3 bytes for the fromAddress, 3 bytes for the toAddress, and 2 bytes for the opcode
24-26 | fromAddress [0-2] | fromAddress of JT operation, index 1
27-29 | toAddress [0-2] | toAddress of JT operation, index 1
30    | opcode byte 0 | opcode of JT operation, index 1, byte 0
31    | opcode byte 1 | opcode of JT operation, index 1, byte 1
32-39 | | fromAddress, toAddress, opcode of JT operation, index 2
... | | 
521-528 | | ... JT operation, index 63

# SRAM Write

The SRAM Write is how you fill the SRAM with the waveforms to be played by the DACs. It hasn't changed for with the Jump Table version of the DACs, but we present the specification here for completeness.

Unlike the jump table, the SRAM is not defined in a single packet. A single SRAM write defines 1024 bytes = 256 words = 1 page of SRAM data, and you must issue as many SRAM Writes as you have pages of data to define. The SRAM data are streamed 1 word per ns to the DACs (14 bits to DAC A, 14 to DAC B, 4 to the ECL serial). Because of this, the SRAM is addressed *by the word*; that is, each SRAM word has its own (sequential) address. As noted previously, SRAM addresses are three bytes, meaning we could address up to 2^24 words of SRAM (although the memory is not that large).

The first two bytes of an SRAM Write ethernet packet (not counting the length header, which is automatically added by the DE server) state the address of the SRAM to be written. Why only two, when we just said that an SRAM address is three bytes? The SRAM Write defines a single page of data, which is 256 words, making the last byte in the address unneccessary. That is, the address given is the higher two bytes in the SRAM address; the first word in the page is written to address [byte 1] + [byte 0] + 00000000, while the last word is written to [byte 1] + [byte 0] + 11111111 (where + indicates concatenation, not addition).

Finally, what about the SRAM word itself? Bits 0-13 define bits 0-13 of DAC A's output, bits 14-27 define bits 0-13 of DAC B's output, and bits 28-31 the ECL serial output.

In table form:

Byte Index (0-indexed) | Name | Description
-----------------------|------|------------
  0 | adrStart[1] | middle byte of SRAM address (bits 8-15)
  1 | adrStart[2] | high byte of SRAM address (bits 16-23)
  2 | sram(0)[0] | low byte of SRAM word at address + 0
  3 | sram(0)[1] | 2nd byte
  4 | sram(0)[2] | 3rd byte
  5 | sram(0)[3] | high byte
6-9 | sram(1)[0-3] | SRAM word at address + 1
... | | 
1022-1025 | sram(255)[0-3] | SRAM word at address + 255

# Register Write

The register write is how you make the board do stuff, i.e. run the JT and SRAM. This *has* changed from the previous version.

Byte Index (0-indexed) | Name | Description
-----------------------|------|------------
0 | start | 0 = no start, 1 = master start SRAM, 2 = test mode, 3 = slave, start on daisy chain. 1 or 3 clears the SRAM count (?)
1 | readback | 0 = no readback, 1 = readback registers after 2 us, 2 = readback after I2C is done (?)
2-12 | I2C stuff | (see documentation)
13-14 | numcycles | number of master SRAM starts (2 bytes)
15-16 | cycledelay | Delay before each start, in us.
17 | JindexA | JT index A. Will count number of times this JT index is called.
18 | JindexB | JT index B. Will count number of times this JT index is called.
43-44 | startdelay | SRAM start delay after daisy chain pulse (2 bytes) (compensate for cable delay)
45 | sync | (see documentation)
46 | ABclock | clock polarity (?)
47-50 | serial | (see documentation)
51 | Mon1 | set Mon1 output
52 | Mon2 | set Mon2 output
53-55 | spare | not used

# Gotchas

* The JT operations take place on the clock cycle *after* the from address is reached. That is, if you idle with a from address of 10, then the SRAM in cell 11 (44-47 ns) will be repeated during the idle.
* The end opcode is offset by two; that is, ending with a from address of 10 will play through cells 10, 11, and 12 and then idle on cell 12.
* From addresses are not allowed to be within two of each other.
