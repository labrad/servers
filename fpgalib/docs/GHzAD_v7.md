# Ethernet Commands for GHzADC

John Martinis

## General specifications

FPGA interface for GHzADC.
There used to be a prototype board, version/build 1, 2 and 6.
These are supposed to have been removed from use.
Do not use them; their pin-out is different from the other board.

The two AD converters on the board are each 8 bits at 1 Gs/s.
To simplify computation, data from adjacent times are summed, giving a net data rate at 500 Ms/s, 9 bits.
This adjacent sample summing is not a anti-aliasing filter, so two (I and Q) channels, this gives a system bandwidth of +- 250 MHz.  

The Ethernet write commands are very similar to the GHzDAC board.
The two basic command types are: 
1. SRAM Write   (to download sine functions)
2. Register Write (controls the board function)  

Ethernet commands have Preamble, Destination, and Source fields, followed by two length bytes and the data bytes.
The SRAM and register commands are recognized according to the value of the length bytes, which gives the total number of bytes of the data field d(1)..d(length).
Ethernet packets are specified to have data-field lengths from 46 to 1500.  

### MAC address

MAC address of card is 00.01.CA.AA.01.(sw), where sw[5..0] is the dipswitch value on the board with on=0.
This address is from a now defunct company of Steve Waltman.
The 01 value if the fifth byte (before 00sw) indicates this is an AD board.
DAC boards use 00 in the fifth byte.

### LEDs


LED[0] light when either FPGA PLL or external 1 GHz PLL not locked/pgrmd  
LED[1] light indicates bad clocking phase of either AD chip  
LED[2] light indicates over range of I input  
LED[3] light indicates over range of Q input  


### Monitors

mon[0] is defined by register, see page below  
mon[1] is defined by register


## SRAM Write

### Genral description

The controller must write to SRAM in the AD board to define two tables,
a retrigger table to define multiple AD triggers for an experiment start,
and a multiplier table for demodulation of the incoming signal for each demodulation channel.

#### Retrigger table

The retrigger table defines multiple AD triggers per master start.
The table starts at address 0, then increments up (to a maximum 127) after performing the functions of each table entry,
until it reaches a table entry with `rdelay[15..8]=0`, at which time the retriggering stops. 
Note that an empty table with `rdelay[15..9]=0` at the address 0 will not ever trigger the AD.
In the table entry, `rdelay[15..0] + 3` is the number of 4 ns cycles between the AD start (or last end of ADon) and the AD trigger.
After this delay, the AD is turned on for `rlength[7..0] + 1` cycles, during which ADon demultiplexer (don) is high.
The value `rcount[15..0] + 1` is the number of AD triggers per table entry.
An AD done signal pulses 3 cycles after the last ADon goes low.
Note that there is approximately 7 clock cycle delay that needs to be measured and taken into account to get demodulation time correct.
Channels 0 to `rchan[3..0] - 1` is read out; maximum `rchan[3..0]` is 11 for 12 channels.
If `rchan[3..0] = 0`, then save data in bit readout mode.
See below.

Note that you have multiple triggers, as for the DAC board.
But for each trigger, you can have multiple retriggering to account for multiple AD demodulations during each sequence.  

#### Mixer table

The multiplier sram table is now 8 bit integers that is multiplied to the input waveforms I and Q.

A standard mixer table would be  
z(n) = w(n dt) exp(-j 2 pi f n dt)  
where I(n) = Re z(n), Q(n) = Im z(n).
This demodulates a signal at frequency f.
w(n) is a real valued window function going to zero at the endpoints which prevents spectral leakage.
Note however, that *any* complex function can be used for z(n).
More sophisticated functions may work better for nulling unwanted sidebands, etc.

The multiplied numbers are then integrated over the waveform with rlength[7..0] clock cycles, as defined in the retrigger table.  

The multiplier values are stored as two bytes of memory for every 2 ns, since the AD is sampling twice every clock cycle).
The total length is 512 addresses every 2 ns, or 1 us in time length.
As a twos-complement number (signed 8-bit number), the maximum multiplier value is `127 = b01111111`, and the minimum value is `-128 = b10000000`.
The computed multiplier function should be converted to integer values with the proper rounding function, not round(x) as it biases positive and negative numbers non-uniformly.  

Write 0 into all unused sine lookup tables to minimize power consumption of the FPGA.

### Write format

Writing into the FPGA SRAM is done in blocks of 1024 bytes, starting at address

    sram(+0)    = (adrstart[20..8],00000000),

and ending at

    sram(+1023) = (adrstart[20..8],11111111). 

#### SRAM memory use (currently maxed out):

    Retrigger    128*4 = 8kb
    Multipliers  8kb for 1 channel
    Averager     4k*8Bytes = 262kb for 16us
    FIFO         .5K*8 = 4kb (need to reduce Averager to increase FIFO size)

#### Retrigger table

The retrigger table is stored in SRAM memory with adrstart[20..8] = 0.  The Ethernet packet is given by

    l(0)    length[15..8]    set to 4; ( length[15..0]= 1024+2=1026 )
    l(1)    length[7..0]     set to 2

    d(0)    adrstart[15..8]    SRAM page for start address: middle bits = 0,
    d(1)    adrstart[23..16]   upper bits; size of SRAM implies bits [23..19] = 0

    d(2)    sram(+0)[7..0]    rcount[7..0](0)    +1 = number AD cycles
    d(3)    sram(+1)[7..0]    rcount[15..8](0)
    d(4)    sram(+2)[7..0]    rdelay[7..0](0)    +4= clock delay before Multiplier on
    d(5)    sram(+3)[7..0]    rdelay[15..8](0)       (units of 4 ns)
    d(6)    sram(+4)[7..0]    rlength(7..0](0)   +1 = clock length of Multiplier on
    d(7)    sram(+5)[7..0]    rchan[3..0](0)     Number channels saved, 0=bit mode
    d(8)    sram(+6)[7..0]    spare
    d(9)    sram(+7)[7..0]    spare

    d(10)   sram(+8)[7..0]    rcount[7..0](1)
    ...
    d(1022)sram(+1023)[7..0]  rcount[15..8](127)
    ...
    d(1025)sram(+1023)[7..0]  spare

#### Mixer table

For the multiplier lookup tables, adrstart is taken from the following table
adrstart[20..8]= channel n + 1.

This offsets by 1 from the above trigger page.

The Ethernet packet for channel n is (in signed int (‘<i1’ for python or ‘int8’):

    l(0)    length[15..8]     set to 4; ( length[15..0]= 1024+2=1026 )
    l(1)    length[7..0]      set to 2

    d(0)    adrstart[15..8]   SRAM page for start address: middle bits = n+1 
    d(1)    adrstart[23..16]  upper bits; size of SRAM implies bits [23..19] = 0

    d(2)    sram(+0)[7..0]    multsin(0)	I0	Multiplier time 0
    d(3)    sram(+1)[7..0]    multcos(0)	Q0
    d(4)    sram(+2)[7..0]    multsin(1)	I1	Multiplier time 1 (1/2 clock, 2ns)
    d(5)    sram(+3)[7..0]    multcos(1)	Q1
    ...
    d(1024)sram(+1022)[7..0]  multsin(511)
    d(1025)sram(+1023)[7..0]  multcos(511)

512 * ns = 1.024us max demod length


## Register Write

These registers control the AD functions.
This card is always set in slave mode for daisychain initiation of AD functions (see GHzDAC board).  

    l(0)    length[15..8]   set to 0  ; ( length[15..0] = 59 )
    l(1)    length[7..0]    set to 59

    d(0)    start[7..0]        Output & command function
                               0 = off
                               1 = register readback
                               2 = average mode, auto start (use n=1)
                               3 = average mode, daisychain start
                               4 = demodulator mode, auto start (use n=1)
                               5 = demodulator mode, daisychain start
                               6 = set PLL of 1GHz clock with ser[23..0], no readback
                               7 = recalibrate AD converters, no readback
    d(1)    startdelay[7..0]   Start delay after daisychain signal, compensates for dchain delays.
    d(2)    startdelay[15..8]      Note longer delays than for GHzDAC
    d(3)    ser1[7..0]         8 lowest PLL bits of serial interface 
    d(4)    ser2[7..0]         8 middle PLL bits
    d(5)    ser3[7..0]         8 highest PLL bits
    d(6)    spare

    d(7)    n[7..0]	           n = Number of averages in average mode
    d(8)    n[15..8]           n = Number of total events in demodulator mode
    d(9)    bitflip[7..0]      XOR mask for bit readout	
    d(10)   mon0[7..0]         SMA mon0 and mon1 programming, like DAC board
    d(11)   mon1[7..0]
    ...
    d(58)   spare


## Register Readback

Registers are readback according to the above data fields and additional bytes given here.
Length of readback = 46.

    l(0)    length[15..8]       set to 0
    l(1)    length[7..0]        set to 46
    d(0)    build[7..0]         Build number of FPGA code.  
    d(1)    clockmon[7..0]      bit0 = NOT(LED1 light) = no PLL in external 1GHz clock 
                                bit1=dclkA output (phase of data stream)
                                bit2=dclkA delayed 1ns output
                                bit3=dclkB output
                                bit4=dclkB delayed 1ns output
    d(2)    trigs[7..0]         Count of number of triggers (same as DAC sramcount) 
    d(3)    trigs[15..8]            reset with start=2,3,4,5
    d(4)    npackets[7..0]      Counter of number of packets received (reg and SRAM)
    d(5)    badpackets[7..0]    Number of packets received with bad CRC 
    d(6)    spare
    ...
    d(45)   spare[7..0]         set to 0


## Demodulator output

After demodulation is done on each retrigger, demodulator output is put into a FIFO from channel 0 to `numchan[7..0]-1`.
Once 11 IQ pairs are in FIFO (44 bytes), or end of all retriggering, the ethernet packet is sent by pulling bytes out of FIFO, 44 bytes per output event.
Use `numchan[7..0]=11` to read back every AD retrigger, since the writing of 44 bytes will immediately trigger a FIFO read.  

The FIFO stores 8192 bytes of data, or 186 packets.
This should be fine except for really long sequences.
If you have many retriggers that are closely spaced, with large number channels, the FIFO will overflow before having a chance to release the data.
The total Ethernet transmission time for one packet is around 5 us.
We have halved the averager size to 8 us to have larger FIFO memory.    

When returning these packets, there is a running count from the end bytes `countpack[7..0]` and `countrb[15..0]` that increases for each packet.
This data enables one to check if any packets were missed or to check for their ordering.    

    l(0)    length[15..8]       set to 0
    l(1)    length[7..0]        set to 48

    d(0)    Idemod0[7..0]       First element of FIFO ; Low byte of demodulator sum
    d(1)    Idemod0[15..8]          High byte
    d(2)    Qdemod0[7..0]       First element of FIFO; Quadrature output
    d(3)    Qdemod0[15..8]
    ...
    d(4)    Idemod1[7..0]       Second element of FIFO
    d(5)    Idemod1[15..8]
    d(6)    Qdemod1[7..0]
    d(7)    Qdemod1[15..8]
    ...
    d(40)   Idemod10[7..0]      11th channel
    d(41)   Idemod10[15..8]
    d(42)   Qdemod10[7..0]
    d(43)   Qdemod10[15..8]

    d(44)   countrb[7..0]       Running count of readback number since last start
    d(45)   countrb[15..8]      1st readback has countrb=1
    d(46)   countpack[7..0]     Packet counter, reset on start
    d(47)   spare [7..0]


In bit readout mode, use `rchan[7..0]=0`.
Readout is only the sign bit of channels 0 to 7; one byte readout is designed for compactness to minimize number of Ethernet packets.
The bit is 0 if real quadrature of the channel is positive.
Bit is flipped with XOR mask `bitflip[7..0]` defined in register write.
Order of bits in output byte is `[ch7..ch0]`.

    l(1)    length[15..8]       set to 0
    l(2)    length[7..0]        set to 48

    d(1)    bits1[7..0]         1st bitstring
    d(2)    bits2[7..0]         2nd bitstring
    ...
    d(44)   bits44[7..0]        44th bitstring

    d(45)   countrb[7..0]       Running count of triggers since last start
    d(46)   countrb[15..8]      1st readback has countrb=1
    d(47)   countpack[7..0]     Packet counter for retriggering, reset when countrb incr
    d(48)   spare [7..0]


## Average Output

Reads back 32kBytes in 16 sequential packets (blocks) of 1024 bytes each.
Takes 4 ms.

    l(1)    length[15..8]       set to 4
    l(2)    length[7..0]        set to 0

    d(1)    Iavg0[7..0]         I channel average, address 0
    d(2)    Iavg0[15..0]        high order bytes of above
    d(3)    Qavg0[7..0]         Q channel average, address 0
    d(4)    Qavg0[15..0]        high order bytes of above

    d(5)    Iavg1[7..0]         I channel for address 1
    d(6)    Iavg1[15..0]
    d(7)    Qavg1[7..0]         Q channel for address 1
    d(8)    Qavg1[15..0]
    ...
    d(1021) Iavg255[7..0]       I channel for address 255
    d(1022) Iavg255[15..0]
    d(1023) Qavg255[7..0]       Q channel for address 255
    d(1024) Qavg255[15..0]


## DaisyChain Connections

    Daisy_Up                        Daisy_Down
    Quartus     Board               Quartus         Board

    Daisy_out[0]    J31(2,1)        Daisy_in[2]     J32(2,1)
    Daisy_out[1]    J31(3,6)        Daisy_in[3]     J32(3,6)
    Daisy_in[0]     J31(5,4)        Daisy_out[2]    J32(5,4)
    Daisy_in[1]     J31(7,8)        Daisy_out[3]    J32(7,8)


In the version GHzDAC, the LVDS are now DC coupled.  

The connectors are labeled Daisy_Up (J31) and Daisy_Down (J32); the highest (master) board is wired from the Daisy_down connector to the Daisy_Up connector of the next board.  

For our pulse (SRAM start) signals, encode the pulse as with previous versions so that it is normally high, and pulses low for the start signal.
This is done by inserting NOT gates at the daisychain output and input lines.

We need to check timing and delay requirements for the new 250 MHz clock, and find what cables give best performance.

    Delays for the old sequencer board:
    FPGA + electronics in and out:      6.8 ns
    Cable delay:                        1.4 ns/ft

                Time delay      0 clock delay   1 clock delay       2 clock delay
    1’ cable    8.2 ns          0-122 MHz       122-200 MHz
    3’ cable    11.0 ns         0-91 MHz        91-182 MHz          182-200 MHz

See GHzDAC for details of up daisy chain.
For the AD measurement bits, the signals are output at Daisyout[0,1]  according to the following:

The output bitstream in the daisy chain will be a simple 1+8 bit serial protocol
Daisyout[0]     ...0 0 0 1 b0 b2 b4 b6 b8 b10 b12 b14 0 0 0 ...
Daisyout[1]     ...0 0 0 1 b1 b3 b5 b7 b9 b11 b13 b15 0 0 0 ...
The bits b0...b15 are 16 output bits of the AD converter, demondulator, and thresholding detector.
Note the 0 to 1 transition is the start of the serial transmission.    



## Output Monitors

### dipswitch DSW[7]=1

    mon[0] = regdone = received Ethernet input for a register write
    mon[1] = ethersend  =  sent Ethernet output initiated by a register readback

2 clock latency

### dipswitch DSW[7]=0

Outputs of mon0 and mon1 are controlled by registers `mon0[7..0]` and `mon1[7..0]` according to the following table. 3 clock latency

    0   REGwrite        Ethernet in, write to registers
    1   SRAMwrite       Ethernet in, write to SRAM memory
    2   start           Start AD converter
    3   aon             On when averaging 
    4   don             On when demodulating
    5   ADdone          ADconverter/demodulator done for one retrigger
    6   alldone         All triggers done for one start
    7   fifo_adv        Read new byte from fifo, 44 pulses total (named data_next)
    8   fifostart       start pulse for fifo read (44 bytes) for packet send
    9   spare 

    10  DaisyIn[0]      DaisyIn[0] signal after fast input FF
    11  DaisyIn[1]
    12  DaisyIn[2]
    13  DaisyIn[3]
    14  DaisyOut[0]     DaisyOut[0] signal before fast output FF
    15  DaisyOut[1]
    16  DaisyOut[2]
    17  DaisyOut[3]

    18  d[0]            This is ADdemodulator output bits (bit readout mode)
    19  d[1]
    ...
    25  d[7]
    26  (d[8])          Not used now
    ...
    33  (d[15])


## Initial Bringup

fpgaTest.py generates ethernet packets and programs the GHzDAC boards to output signals for these tests.

1. General functionality:
  1. Power up, and check led(0) is off (FPGA locked), and led(1) is on (GHz PLL unlocked).
  2. Write to board and read back, showing build number and Clock_Mux not locked.
  3. Write to board to set PLL, and check led(1) goes off.  Use same PLL shift data as for GHzDAC.
  4. Input AC signal into I and/or Q AD input, and check large (~0.5 V) signal causes led(2) for I and led(3) for Q to go on. This checks AD and over range function.
2. Average mode:
  5. Input as above, but send command for 1 average, auto start.  Look at downloaded data, and check that it oscillates properly.  Check that aon goes high for 8 us after auto ethernet command is sent (see Output Monitors section for how to send aon to monitor output).
  6. As above, but inject triangle wave at 100 kHz, with amplitude just above saturation.  Amplitude should go up and down smoothly, with no jumps from missing bits of the AD converter.  Both channels should track for simultaneous inputs.
  7. Input a repetive waveform, and check that averaging (summing) function works, with waveform getting bigger with larger n.
3. Demodulator mode:
  8. Input 10MHz tone, 1/4 scale. Scan mixer table frequency with square envelope. This is using the AD board as a spectrum analyzer with a very leaky envelope. Observe measurement of side lobes with sinc dependence.
  9.  For a filter function more like a gaussian, check if the measured spectrum looks smoother, as expected.
  10. Set only one mixer table entry to non-zero. Scan over time slice so that mixer table acts like sampling oscilloscope. Check that signal matches what is observed via average mode.
  11.  Check demodulation value at wrong sideband, and check if consistent with wrong sideband tone observed when averaged.  
  12. Repeat for all possible channels.  


### Revision history

#### Version 7: Oct 2014-5-24

* Revise to include 12 channels; demodulation channels 0 to 11 are currently working.
* Major change, remove sine tables and phase accumulation, replace with multiplier table.
* Remove filter function before sine multiplication.  
* Only filter/demodulate 8 bits address = 1 us
* Averaging Memory is halved to 8 us.
* Can define now output data for packet.
* FIFO is 8192 bytes; this is 186 ethernet packets.
* Fixed ugly code, now Ethernet input is first latched.
* Added counter for received packet and bad CRC packet.
* Build = 7

#### Version 6: Oct 2013-10-29

* Revise version 2 to include 6 channels
* Build = 6

#### Version 5: Oct 2013-10-28

* Revise version 3 to include 6 channels
* Build = 5 

#### Version 4: Aug. 2013

* Add multiple triggering, fifo on output data, single bit output mode
* Fifo output data, Daisy chain output from ADbits, enhanced monitors like DAC
* Build = 4

#### Version 3:  Do not use on prototype board (as FPGA pinouts have changed)

* Add DCLK and outedge capability, as built into Board 1.0/not prototype
* outedge=0 always.  DCLK phase in clockmon[1] output. 
* Change LED[0] and LED[1] programming 
* Build=3

#### Version 2:

* Add counter for sram trigger  
* Add its readback register  
* Build=2

#### Version 1:

* Only 4 (addresses 0 to 3) of the 11 demodulation channels are compiled
* Build=1
