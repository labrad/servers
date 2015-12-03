# Ethernet Commands for GHzDAC

John Martinis


## Revision History

### Code for GHzDAC, version 3 of FPGA

Ethernet commands have Preamble, Destination, and Source fields that are automatically included with the driver module.
For SequenceV1, two basic commands are possible: (1) SRAM Write or (2) Register Write for control of the sequencer.
These two commands are recognized according to the value of the first two length bytes, given below, which gives the total number of bytes of the following data field `d(1)..d(length)`.
In general, ethernet packets can have data-field lengths from 46 to 1500.

MAC address of card is `0.1.202.170.0.(00sw)` (i.e. `00:01:CA:AA:00:..`), where `sw[5..0]` is the dipswitch value on the board with `on=0`.

Check I2C lines if need to add resistor for slow slew rate.

* `LED[0]` light indicates FPGA 250MHz PLL not locked
* `LED[1]` light indicates external 1 GHz PLL not locked (or not programmed)
* `LED[3]` light is latched of notlocked internal 1GHzDAC serializer PLL

* `mon[0]` is pulsed high for 4 ns at beginning of SRAM sequence (for triggering).
* `mon[1]` is 250 MHz clock

The data in SRAM is streamed 4 bytes each ns to the DAC converters and ECL output.


### V4; May 24, 2008

* Added bit for 0 or 1 page of memory, set by `start[7]` bit
* `MEMadrstart[15..8]` set to 0 or 1 to define page of mem write.
* Issac’s output: `mon[1]` set to serial0.
* Fix: start resets MemAdr to 0 in AddressControl, always restarts sequence.
* All phases on LVDS set to 90 degrees.
* Software-build constant set to 5. Program files: GHzDAC_V4_S5
* Added 2nd block of SRAM (2048 ns) to present memory (8192 ns).
  Write to new SRAM with addresses corresponding to times 8192 to 8192+2048-1 ns.
  For readout, the address of this 2nd block is offset by `SRAMoffset[7..0]`*1024 ns.
  When reading addresses in this offset range, the previous SRAM value is output.


### GHzDAC_V5

* Added comments on daisychain
* Add idle=3 to Master/Slave mode
* 16 bits for start delay; d(52) from spare to `startdelay[15..8]`
* sram_big module for larger FPGA
* Software-build constant set to 8 for big FPGA EPS30F484.
  Software-build constant set to 7 for small FPGA EP2S15F484.


### GHzDAC_V6

Various test programs


### GHzDAC_V7

* Add counter and readback register for SRAM trigger
* `mon[0]=sram` started
* `mon[1]=sramtrig` (now counted)
* Software-build constant set to 12 for big FPGA EPS30F484.
  Software-build constant set to 11 for small FPGA EP2S15F484.


### GHzDAC_V8; April 2013

This is a major revision. Changes are:

1. Take out memsequence code, just replacing it with immediate SRAM call
   with a repeating call after a programmable delay.
   There is now no output on the Ethernet generated from the memsequence timer.
2. Pass 16 measurement signals via two Daisychain lines UP the chain.
   Note that master start command passes timing pulse DOWN the chain.
3. Include JumpTable for repeated sequences and conditional jumps.
   SRAMoffset and multiblock removed since can use counter and jumps for delay.
4. Idles at end address after SRAM sequence.
5. Start command coded differently, with no slave register, to make more clear.
6. Register write selects output monitors, `mon[0]` and `mon[1]`.
7. Register output counters for SRAMstart, SRAMend, 2 JumpIndex values
8. Software-build constant set to 13 for small FPGA EP2S15F484.
   Software-build constant set to 14 for big FPGA EP2S30F484.


## SRAM Write:

Writes into SRAM (now on FPGA) a total of 256 words (each 32 bits long, 4 bytes).

Starting at address `sram(+0) = (adrstart[20..8],00000000)`, and ending at `sram(+255) = (adrstart[20..8],11111111)`.

Each group of 256 words is referred to as a “derp.”

The data is streamed 1 word (32 bits / 4 bytes) per ns into the DAC converters and ECL outputs.
LVDS serializers stream 4 words per clock cycle at 250 MHz (4ns).

NOTE: lowest two bits of SRAMstart set to [00] and SRAMend set to [11] in present version of software to simplify serialization code.

Normal memory block is 8K SRAM words, or 5 bits of `adrstart[12..8]`.
This gives 8 us of programming (but see Multi-block function below).
Each word has the following format:

    DACA[13..0]  = bits[13..0]    For D/A converter A output
    DACB[13..0]  = bits[27..14]   ForD/A converter B output
    SERIAL[3..0] = bits[31..28]   For ECL serial output

The full SRAM Write packet is as follows:

    l(1)  length[15..8]   set to 4; ( length[15..0]= 256*4+2=1026 )
    l(2)  length[7..0]    set to 2

    d(1)  adrstart[15..8]   Page for start address: middle bits,
    d(2)  adrstart[23..16]  upper bits; size of SRAM implies bits [23..19] = 0

    d(3)  sram(+0)[7..0]    Writes bits [7..0]   at address [adrstart[23..8],0]
    d(4)  sram(+0)[15..8]   Writes bits [15..8]  at address [adrstart[23..8],0]
    d(5)  sram(+0)[23..16]  Writes bits [23..16] at address [adrstart[23..8],0]
    d(6)  sram(+0)[31..24]  Writes bits [31..24] at address [adrstart[23..8],0]

    d(7)  sram(+1)[7..0]    Writes bits [7..0]   at address [adrstart[23..8],1]
    d(8)  sram(+1)[15..8]   Writes bits [15..8]  at address [adrstart[23..8],1]
    d(9)  sram(+1)[23..16]  Writes bits [23..16] at address [adrstart[23..8],1]
    d(10) sram(+1)[31..24]  Writes bits [31..24] at address [adrstart[23..8],1]
    ...
    d(1023) sram(+255)[7..0]    Writes bits [7..0]   at address [adrstart[23..8],255]
    d(1024) sram(+255)[15..8]   Writes bits [15..8]  at address [adrstart[23..8],255]
    d(1025) sram(+255)[23..16]  Writes bits [23..16] at address [adrstart[23..8],255]
    d(1026) sram(+255)[31..24]  Writes bits [31..24] at address [adrstart[23..8],255]


## JumpTable Write:

This similar to memory write for memsequencer, but now it loads in data for jumptable.
The data consists of 16 bytes of CountTo counter limits and 64*8 bytes of Jumptable entries.

fromAddr and toAddr are addresses of 4ns blocks. If we set StartAdr `d(17..19)` to 0 and a jump table END with FromAdr=10, SRAM will run for 10*4ns=40ns before hitting the END command.

    l(1)  length[15..8]   set to 2  (528 = 16+64*8)
    l(2)  length[7..0]    set to 16

    d(1)  CountTo0[7..0]  CountTo0[31..0] is maximum count of counter 0
    d(2)  CountTo0[15..8]
    d(3)  CountTo0[23..16]
    d(4)  CountTo0[31..24]

    d(5)  CountTo1[7..0]  CountTo1[31..0] is for counter 1
    ...
    d(16) CountTo3[7..0]  CountTo3[31..0] is for counter 3

    d(17) StartAdr[7..0]    3 bytes for StartAdr[23..0]
    d(18) StartAdr[15..8]
    d(19) StartAdr[23..16]
    d(20) StartAdr[7..0]    Must be equal to d(17),d(18),d(19)
    d(21) StartAdr[15..8]
    d(22) StartAdr[23..16]
    d(23) StartOpCode[7..0]  =5 for NOP
    d(24) StartOpCode[15..8] =0

    d(25) FromAdr(1)[7..0]  3 bytes for FromAdr(1)[23..0]-1, jumptable index=1
    d(26) FromAdr(1)[15..8]
    d(27) FromAdr(1)[23.16]
    d(28) ToAdr(1)[7..0]    3 bytes for ToAdr(1)[23..0]
    d(29) ToAdr(1)[15..8]
    d(30) ToAdr(1)[23.16]
    d(32) OpCode(1)[7..0]   2 bytes for OpCode(1)[15..0]
    d(32) OpCode(1)[15..8]

    d(33) FromAdr(2)[7..0]  Bytes for FromAdr(2)[23..0]-1, index=2
    ...
    d(528) OpCode(63)[15..8] Bytes for OpCode(63)[15..8], index=63


### Operation codes for JumpTable:

    dddddddd ddddddd0   IDLE: extra d[14..0] 4ns clocks (max 128 us)
                          (2**15)-1 *4ns = 131068ns

    xxjjjjjj iiiin001   CHECK: if daisychain bit(index=iiii) = n
                          T:          jump ToAdr, load JumpIndex jjjjjj
                          F:          AdrCounter+1,    JumpIndex+1

    xxjjjjjj xxxx1101   JUMP:         jump ToAdr, load JumpIndex jjjjjj

    xxxxxxxx xxxx0101   NOP:          AdrCounter+1,    JumpIndex+1

    xxjjjjjj xxccx011   CYCLE: until count(ind=cc) = CountTo(ind=cc)
                          F: count+1, jump ToAdr, load JumpIndex jjjjjj
                          T: count=0, AdrCounter+1,    JumpIndex+1

    xxxxxxxx xxxxx111   END: SRAMend, stops Adr counting at FromAdr+2

    x=do not care.

JumpTable addresses FromAdr must be 1 less than actual address (due to pipelining).
For StartAdr (index=0 of JumpTable), set FromAdr and ToAdr to actual address.
For END, set FromAdr to 2 less than actual stop address, where Adr will idles.
ToAdr is actual value.

`CHECK` evaluated at address FromAdr+1

`IDLE` produces d+1 clock cycles at address FromAdr+1; ToAdr is not used.
Setting `d[14..0]` to 0 produces 1 clock cycle of delay for the instruction itself.
FromAdr must be separated by 4 or more from other FromAdr’s (due to pipelining).

The first JumpTable command at index=0 is the start instruction, which should be NOP (opcode=05).
Counters `count(index=0 to 3)` are all cleared at SRAMstart pulse, or when count is done.

#### JumpTable Compiler

JumpIndex `jjjjjj` points to FromAdr in Jumptable where next opcode evaluated.
You must keep track of program flow for both ToAdr and JumpIndex.
Not as convenient as normal computer, but done here for speed and efficiency of FPGA coding.
Compiler steps are:

1. For SRAM sequence, have table of StartAdr, FromAdr, ToAdr, EndAdr and opcodes
2. Subtract 0 for StartAdr and ToAdr, 1 for FromAdr, and 2 for EndAdr
3. Order FromAdr in increasing values, and assign index 0,1,2,3, ...  StartAdr is index=0.
4. Check that FromAdr values are spaced 4 or greater.
5. Critical step for FPGA sequencing: For each ToAdr, find the next FromAdr and its index.
   Use this index for the opcode associated with the ToAdr.

For example code, numbers are (index), OpCode, ToAddr, FromAddr

Normal sequence:

    (0)  0005 000000 000000 START at StartAdr=0
    (1)  0007 000000 000050 sequence Adr until END at Adr=52

Spin echo:

    (0)  0005 000007 000007 START at StartAdr=7
    (1)  0200 000000 000010 sequence Adr until IDLE at Adr=11 for 257 total cycles
    (2)  0400 000000 000020 sequence Adr until IDLE at Adr=21 for 513 total cycles
    (3)  0007 000000 000050 sequence Adr until END at Adr=52

Test for all operations:

    (0)  0005 000003 000003 START at StartAdr=3
    (1)  0129 000007 000010 CHECK bit(2) = 1; T: jump to ToAdr=7 (index=1)
    (2)  0213 000028 000030 CYCLE until count(1) = CountTo(2);
                                    F:  jump to ToAdr=28 (index=2)
    (3)  040D 000048 000040 JUMP to ToAdr=48 (index=4)
    (4)  0004 000000 000050 IDLE 2 cycles (3 cycles total at Adr=51)
    (5)  0007 000000 000060 END at Adr=62 


## Register Write:

These registers control the SRAM sequencer and I2C interface.  

    l(1)   length[15..8]   set to 0  ; ( length[15..0] = 56 )
    l(2)   length[7..0]    set to 56

    d(1)   start[7..0]   start[1..0] is command for SRAM sequencer: 
              0 = no start, daisy pass thru
              1 = master start of SRAM
              2 = test mode, continuous output from dreg15..0
              3 = slave, start on daisy chain
              Clears SRAMcount on 1 or 3
    d(2)   readback[7..0]    Readback command:
              0 = no readback,
              1 = readback of registers after 2 us (enough for serDAC),
              2 = readback of registers after I2C is done.
    d(3)   stopI2C[7..0]       Stop bytes for I2C (see below).  0 for no operation
    d(4)   readwriteI2C[7..0]  Read/Write byte for I2C
    d(5)   ackI2C[7..0]        Acknowledge byte for I2C
    d(6)   data7[7..0]         Last I2C data byte
    d(7)   data6[7..0]
    d(8)   data5[7..0]
    d(9)   data4[7..0]
    d(10)  data3[7..0]
    d(11)  data2[7..0]
    d(12)  data1[7..0]
    d(13)  data0[7..0]         First I2C data byte

                       start=1            start = 2
    d(14)  dreg0[7..0] numcycles[7..0]    word1[7..0]     Num. of master SRAM starts.
    d(15)  dreg1[7..0] numcycles[15..8]   word1[15..8]      (0 gives no start)
    d(16)  dreg2[7..0] cycledelay[7..0]   word1[23..16]   Delay before each SRAM loop.
    d(17)  dreg3[7..0] cycledelay[15..8]  word1[31..24]     In us; 0 = no delay
    d(18)  dreg4[7..0] JindexA[7..0]      word2[7..0]     Index of counter in JumpTable
    d(19)  dreg5[7..0] JindexB[7..0]      word2[15..8]
    d(20)  dreg6[7..0]                    word2[23..16]
    d(21)  dreg7[7..0]                    word2[31..24]
    d(22)  dreg8[7..0]                    word3[7..0]
    d(23)  dreg9[7..0]                    word3[15..8]
    d(24)  dreg10[7..0]                   word3[23..16]
    d(25)  dreg11[7..0]                   word3[31..24]
    d(26)  dreg12[7..0]                   word4[7..0]
    d(27)  dreg13[7..0]                   word4[15..8]
    d(28)  dreg14[7..0]                   word4[23..16]
    d(29)  dreg15[7..0]                   word4[31..24]
    ...
    d(43)  dreg29[7..0]    dreg31[7..0], dreg30[7..0], … , dreg0[7..0] = reg[255..0]


    d(44)  startdelay[7..0]  SRAM start delay after master initiate or daisychain
    d(45)  startdelay[15..8]   (used to compensate for daisychain delays)

    d(46)  sync[7..0]        Synchronize master start, use to phase lock to microwaves 
                               sync[7..0]+1 is length of a counter that continuously runs 
                               0 = immediate start (normal operation) 
                               249 = start only at every 250 clock cycles = 1 us
                               New value to register changes phase lock
                               Only affects start of master

    d(47)  ABclock[7..0]     Clock polarity of DAC; DACA=bit0 (Enable: bit4) 
                               B=bit1 (Enable: bit5)
                               bit7=reset 1GHz PLL pulse

    d(48)  serial[7..0]      Serial interface (see HardRegProgram file)
                               0 = no operation, 1=PLL, 2=DACA, 3=DACB
    d(49)  ser1[7..0]        8 lowest PLL bits   DAC data
    d(50)  ser2[7..0]        8 middle PLL bits   DAC command data
    d(51)  ser3[7..0]        8 highest PLL bits
    d(52)  Mon0[7..0]        Select Mon0 output
    d(53)  Mon1[7..0]        Select Mon1 output
    d(54)                    Not readback
    d(55)                    Not readback
    d(56)  spare[7..0]       Not readback


## Register Readback:

Registers are readback according to the above data fields and additional bytes given here. Length of readback = 70.

    d(52)  build[7..0]         Build number of FPGA code.  
    d(53)  SRAMcount[7..0]     Count of number of starts of sram
    d(54)  SRAMcount[15..8]    reset with start=1;
    d(55)  JcountA[7..0]       Count of number times IndexA/B called in JumpTable
    d(56)  JcountB[7..0]         in last (one) SRAMstart
    d(57)  serDAC[7..0]        Readback byte of serial DAC interface
    d(58)  sermon[7..0]        ClockMux=bit0, A_IRQ=bit1, B_IRQ=bit2 
    d(59)  clockmon[7..0]      bit0=Aclock, bit1=Bclock, bit7=noPLLlatch=LED3
    d(60)  spare[7..0]
    d(61)  spare[7..0]

    d(62)  ackoutI2C[7..0]     Acknowledge output byte
    d(63)  data7[7..0]         I2C output data, last data byte
    d(64)  data6[7..0]
    d(65)  data5[7..0]
    d(66)  data4[7..0]
    d(67)  data3[7..0]
    d(68)  data2[7..0]
    d(69)  data1[7..0]
    d(70)  data0[7..0]         First data byte

### I2C Interface:

A custom I2C interface is used for the FPGA.  Register definitions are:

    stopI2C[7..0]   Stop bytes for I2C.  Set bit=1 to indicate number of I2C bytes.
          “10000000” indicates 1 byte
          “00100000” indicates 3 bytes
          “00000000” indicates no operation
    readwriteI2C[7..0]  Read or write operation for each byte.  Read=1, Write=0
    ackI2C[7..0]        Acknowledge output bits for reading of a byte (0=ack)
    data7[7..0]         Last data byte to be sent 
    data6[7..0]
    data5[7..0]
    data4[7..0]
    data3[7..0]
    data2[7..0]
    data1[7..0]
    data0[7..0]   First data byte to be sent

#### Example

Suppose we wish to do the following:

* Write 1st byte “7” and get acknowledge bit 1
* Read 2nd byte “4” and send acknowledge bit 0
* Read 3rd byte “F” and send acknowledge bit 1

Then we would send a Register Write command as follows:

    stopI2C =      00100000  Indicates 3 bytes total
    readwriteI2C = 01100000  Write 1st byte, read 2nd and 3rd
    ackI2C =       x0100000  Acknowledge bits for read bytes (x=don’t care)
    data7..0 =     00000xx7  Actual byte data to send

The Register Readback would then contain:

    ack_out =      00100000  (note data wrapped around to left bits
    data_out7..0 = F4700000  & bytes, write_acknowledge=0)


## DaisyChain Connections

### Daisy Up

| Quartus        | Board      |
|----------------|------------|
| `Daisy_out[0]` | `J31(2,1)` |
| `Daisy_out[1]` | `J31(3,6)` |
| `Daisy_in[0]`  | `J31(5,4)` |
| `Daisy_in[1]`  | `J31(7,8)` |

### Daisy Down

| Quartus        | Board      |
|----------------|------------|
| `Daisy_in[2]`  | `J32(2,1)` |
| `Daisy_in[3]`  | `J32(3,6)` |
| `Daisy_out[2]` | `J32(5,4)` |
| `Daisy_out[3]` | `J32(7,8)` |


In the version GHzDAC, the LVDS are now DC coupled.

The connectors are labeled `Daisy_Up` (J31) and `Daisy_Down` (J32).
The highest (master) board is wired from the `Daisy_Down` connector to the `Daisy_Up` connector of the next board.

For our pulse (SRAM start) signals, encode the pulse as with previous versions so that it is normally high, and pulses low for the start signal.
This is done by inserting NOT gates at the daisychain output and input lines.

We need to check timing and delay requirements for the new 250 MHz clock, and find what cables give best performance.

Delays for the old sequencer board:

* FPGA + electronics in and out:  6.8 ns
* Cable delay:  1.4 ns/ft

|          | Time delay | 0 clock delay | 1 clock delay | 2 clock delay |
|----------|------------|---------------|---------------|---------------|
| 1’ cable | 8.2 ns     | 0-122 MHz     | 122-200 MHz   |               |
| 3’ cable | 11.0 ns    | 0-91 MHz      | 91-182 MHz    | 182-200 MHz   |

### Note added Jan 2011:

As seen above, one gets a 3 clock delay at 250 MHz.
This gives 5 clock total delay from board to board since there are 2 internal flip-flops in the daisy chain pipline.
The start delay should increase by 5 from board to board down the daisy chain, but we think people are using 4.
This needs to be checked.

### V8

For the DaisyChain UP signaling, the board sequence is:

    DACmaster -> DAC1 -> DAC2 -> AD1 -> DAC3 -> DAC4 -> AD2

Here, AD1 puts output state measurements on the daisychain, which then communicates to boards higher up, ie DAC2, then DAC1, and then DACmaster.
The same thing happens with AD2, communicating with DAC4 and DAC3.
This data stops being communicated at an AD board because of its programming, which only outputs data from that board.
With this hardware you have to arrange in sequence the DAC and AD boards so that they communicate properly.

Presently, the master start signal is sent through each board, wired as `Daisyin[0]` as input, through an input and output FF, to `Daisyout[2]` as output.

For the measurement line communication, signal flows backwards as compared to master start synchronization.
The input of each board will be `Daisyin[2,3]`, and the output `Daisyout[0,1]`.

The bitstream in the daisy chain will be a simple 1+8 bit serial protocol:

    Daisyin[2]  ... 0 0 0 1 b0 b2 b4 b6 b8 b10 b12 b14 0 0 0 ...
    Daisyin[3]  ... 0 0 0 1 b1 b3 b5 b7 b9 b11 b13 b15 0 0 0 ...

The bits `b0 ... b15` are 16 output bits of the AD converter, demondulator, and thresholding detector.
Note the 0 to 1 transition is the start of the serial transmission.


## Hardware Issues

I found in recompiling the GHzDAC code that the serial programming of the FPGA via the on-board memory (.pof programming)  does not always work.
This happened with a second board, but does not happen with original compiled software.
If I touch the `CONF_DONE` lead with metal, then it the serial configuration loads fine.
This CONF_DONE pin is a FPGA output that goes high when configuration is complete.
This seems to be a problem connected to both hardware and software, and the problem may come from noise on the wire, as it is pulled high by a 10k resistor, which confuses the FPGA and causes a configuration restart.
The fix is to  place a 1 nF capacitor to ground at the CONF_DONE pin, which is convieniently located at the 10 pin header.  


## Output Monitors

When dipswitch `DSW[7]=1`:

* `Mon[0]` = regdone = received Ethernet input for a register write
* `Mon[1]` = ethersend = sent Ethernet output initiated by a register readback

When `DSW[7]=0`:

Outputs of `Mon[0]` and `Mon[1]` are controlled by registers `MonA[7..0]` and `MonB[7..0]` according to the following table:

    0 regdone       Ethernet in, write to registers
    1 SRAMwrite     Ethernet in, write to SRAM memory
    2 Jumpwrite     Ethernet in, write to JumpTable
    3 ethersend     Ethernet out
    4 master start  Master mode start
    5 SRAM running  Start by master or slave, for each cycle
    6 END           END opcode executed at FromAdr, produce 1 cycle pulse
    7 CYCLE
    8 CHECK 
    9 IDLE

    10  DaisyIn[0]  DaisyIn[0] signal after fast input FF
    11  DaisyIn[1]
    12  DaisyIn[2]
    13  DaisyIn[3]
    14  DaisyOut[0] DaisyOut[0] signal before fast output FF
    15  DaisyOut[1]
    16  DaisyOut[2]
    17  DaisyOut[3]

    18  d[0]        This is latched serial input (AD bits) from DaisyUp chain
    19  d[1]
    ...
    33  d[15]
