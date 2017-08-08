# fpgatools

from labrad.types import Value
from labrad.units import V, Hz, us
from labrad.util import linspace
import pdb
##################
# utility methods

def toFloat(num, units):
    if hasattr(num, 'unit'):
        return num[units]
    elif isinstance(num, tuple):
        return Value(*num)[units]
    return num

def binaryDigitsToNum(digits):
    N = len(digits)
    return sum(d*2**(N-1-i) for i, d in enumerate(digits))

def flatten(L):
    """Convert a (possibly) nested list into one flat list."""
    newList = []
    subList = [isinstance(e, list) for e in L]
    lh = rh = 0
    while 1:
        try:
            # look for a sublist in the remaining elements
            rh = lh + subList[lh:].index(True)
            newList.extend(L[lh:rh])
            newList.extend(flatten(L[rh]))
            lh = rh = rh + 1
        except ValueError:
            # no more sublists, so just add the rest
            newList.extend(L[lh:])
            return newList


#######################
# probability functions

def probabilities(switches, qubits, freq=25):
    """Convert switching times to probabilities for multipule qubits."""
    N = len(switches[0])
    assert N > 0
    for s in switches:
        assert isinstance(s[0], (long, int))
        assert len(s) == N
        
    states = zip(*[switchToState(s, q, freq) for s, q in zip(switches, qubits)])
    counts = [0] * 2**len(qubits)
    for s in states:
        counts[binaryDigitsToNum(s)] += 1
    return [float(count) / float(N) for count in counts]

def switchToState(switches, qubit, freq=25):
    """Convert switching times to 0 or 1-state results."""
    cutoff = qubit.cutoff
    freqMHz = toFloat(cutoff, 'MHz')
    cutoffClk = toFloat(cutoff, 'us') * freqMHz
    
    if qubit.is1bigger:
        states = [int(switch > cutoffClk) for switch in switches]
    else:
        states = [int(switch <= cutoffClk) for switch in switches]
    return states

def oneProbability(switches, cutoff, is1bigger, freq=25, minSwitch=0, maxSwitch=150):
    """Convert switching times to 1-state probability."""
    if len(switches) == 0:
        return None
    assert isinstance(switches[0], (long, int))

    freqMHz = toFloat(freq, 'MHz')
    cutoffClk = toFloat(cutoff, 'us') * freqMHz
    maxSwitchClk = toFloat(maxSwitch, 'us') * freqMHz
    minSwitchClk = toFloat(minSwitch, 'us') * freqMHz

    switches = [s for s in switches if s < maxSwitchClk and s > minSwitchClk]
    ones = sum(switch > cutoffClk for switch in switches)
    p1 = float(ones) / float(len(switches))
    if not is1bigger:
        p1 = 1 - p1
    return p1
    

###############
# FPGA commands
#
# these functions generate individual FPGA commands
# the commands must be combined in a list, sent to the
# FPGA, and executed

START = NOOP = 0L
END = 0xf00000L

INIT_TIMER = 0x400000L
STOP_TIMER = 0x400001L

# standard fiber assignments
FLUX = 0
SQUID = 1

def voltageToDAC(val):
    """Converts (value, units) or PhysicalQuantity to a DAC value."""
    return voltsToDAC(toFloat(val, 'V'))

def voltsToDAC(volts):
    """Converts voltage in volts to 16-bit DAC value."""
    return long(round((volts + 2.5) * 13107)) & 0xffff

def milivoltsToDAC(milivolts):
    """Converts voltage in milivolts to 16-bit DAC value."""
    return long(round((milivolts + 2500) * 13.107)) & 0xffff

def switchDAC(fiberID, dacID, slow=False):
    """Switch a DAC to one of its outputs."""
    commands = {
        (0, True): 0x50000L,
        (1, False): 0x50001L,
        (1, True):  0x50002L
    }
    assert fiberID in (0, 1), "fiber ID is %s, needs to be in (0,1)" % fiberID
    assert (dacID, slow) in commands, "(%s, %s) not in commands: %s" %(dacID, slow, commands)
    return 0x100000L * (fiberID + 1) + commands[(dacID, slow)]

# def setDAC(fiberID, dacID, value):
    # """Set the value of a DAC output."""
    # commands = {
        # 0: 0x60000L,
        # 1: 0x70000L
    # }
    # assert fiberID in (0, 1)
    # assert dacID in commands
    # assert value == value & 0xffff
    # return 0x100000L * (fiberID + 1) + commands[dacID] + (value & 0xffff)

def setDAC2(fiberID, dacID, value, slow = False):
    """Set the value of a DAC output."""
    commands = {
        0: 0x00000L,
        1: 0x80000L
    }
    assert fiberID in (0, 1)
    assert dacID in commands
    assert value == value & 0xffff
    if slow:
        return 0x100000L * (fiberID + 1) + commands[1] + ((value & 0xffff) << 3) + (1<<2)
    else:
        return 0x100000L * (fiberID + 1) + commands[1] + ((value & 0xffff) << 3)
    
# def setDACvoltage(fiberID, dacID, voltage):
    # """Set a DAC output to a value in volts."""
    # return setDAC(fiberID, dacID, voltageToDAC(voltage))

def setDACvoltage2(fiberID, dacID, voltage, slow = False):
    """Set a DAC output to a value in volts."""
    return setDAC2(fiberID, dacID, voltageToDAC(voltage), slow = slow)

    
##def setDACvoltage2(fiberID, dacID, voltage):
##    """Set a DAC output to a value in volts."""
##    return setDAC2(fiberID, dacID, voltageToDAC(voltage))

def callSRAM((start, end)):
    """Call an SRAM sequence specified by start and end address."""
    return [0x800000L + (start & 0xfffff),
            0xa00000L + (end & 0xfffff),
            0xc00000L]

def delay(val, freq=25):
    """Delay for some length of time."""
    return delayus(toFloat(val, 'us'), freq)

def delayus(us, freq=25):
    return delayClk(us * freq)

def delayClk(cycles):
    """Delay for some number of clock cycles.

    This may return multiple memory instructions, if the
    delay is longer than can be specified with one command.
    """
    assert cycles >= 2
    cycles -= 2
    cmd = []
    while True:
        c = min(cycles, 0xfffff)
        cycles -= c
        cmd.append(long(0x300000 + c))
        if cycles <= 0:
            break
    return cmd


def explainFPGACommand(cmd):
    """Return a human-readable string describing a given FPGA command."""
    opcode = (cmd & 0xF00000) >> 20
    abcde  = (cmd & 0x0FFFFF)
    xy     = (cmd & 0x00FF00) >> 8
    ab     = (cmd & 0x0000FF)

    if opcode == 0x0:
        return 'No op'
    if opcode == 0x1:
        return 'Send %s on fiber 0' % hex(abcde)
    if opcode == 0x2:
        return 'Send %s on fiber 1' % hex(abcde)
    if opcode == 0x3:
        cycles = abcde + 2
        return 'Delay %d cycles (=%dns)' % (cycles, cycles*40)
    if opcode == 0x4:
        cmds = {0: 'Initiate timer.',
                1: 'Hard-stop timer and send results',
                2: 'Record/Send SRAM timer (not impl.)'}
        return cmds[abcde]
    if opcode == 0x8:
        return 'SRAM start address %s' % hex(abcde)
    if opcode == 0xA:
        return 'SRAM return address %s' % hex(abcde)
    if opcode == 0xC:
        return 'Call SRAM.'
    if opcode == 0xF:
        return 'End of sequence (branch to MEM 0x0)'
    raise Exception('Unknown FPGA command: %s.' % hex(cmd))


def cmdTime(cmd):
    """A conservative estimate of the number of cycles a given command takes."""
    opcode = (cmd & 0xF00000) >> 20
    abcde  = (cmd & 0x0FFFFF)
    xy     = (cmd & 0x00FF00) >> 8
    ab     = (cmd & 0x0000FF)

    if opcode in [0x0, 0x1, 0x2, 0x4, 0x8, 0xA]:
        return 1
    if opcode == 0xF:
        return 2
    if opcode == 0x3:
        return abcde + 1 # delay
    if opcode == 0xC:
        return 250*8 # maximum SRAM length is 8us


def sequenceTime(sequence, freq=(25, 'MHz')):
    """Conservative estimate of the length of a sequence in seconds."""
    cycles = sum(cmdTime(c) for c in sequence)
    t = float(cycles) / toFloat(freq, 'Hz')
    return t


#######################
# FPGA Memory Sequences
#
# these functions build up complete memory sequences
# that can be sent to an FPGA and executed

def resetQubit(bias1, bias2=None,
               count=3, DAC=FLUX):
    if bias2:
        return [
            switchDAC(DAC, 1), delay(10*us),
            [setDACvoltage(DAC, 1, bias1), delay(40*us),
             setDACvoltage(DAC, 1, bias2), delay(40*us)] * count
        ]
    else:
        return [
            switchDAC(DAC, 1), delay(10*us),
            setDACvoltage(DAC, 1, bias1), delay(100*us)
        ]
        
def resetQubit2(bias1, bias2=None,
               count=3, DAC=FLUX):
    if bias2:
        return [
            # switchDAC(DAC, 1), delay(10*us),
            [setDACvoltage2(DAC, 1, bias1), delay(40*us),
             setDACvoltage2(DAC, 1, bias2), delay(40*us)] * count
        ]
    else:
        return [
            # switchDAC(DAC, 1), delay(10*us),
            setDACvoltage2(DAC, 1, bias1), delay(100*us)
        ]

def triangleWave(center=0*V, amplitude=1*V,
                 frequency=250*Hz, steps=30, loopForever=True,
                 withTimer=False, DAC=SQUID):
    """Generate a triangle waveform, suitable for looping."""
    steplen = (1/frequency) / 4 / steps
    
    voltages = linspace(center, center + amplitude, steps)\
             + linspace(center + amplitude, center - amplitude, steps*2)\
             + linspace(center - amplitude, center, steps)

    cmds = [[setDACvoltage2(DAC, 1, v), delay(steplen)] for v in voltages]
    seq = [START,
           switchDAC(DAC, 1, slow=True), delay(10*us),
           cmds,
           switchDAC(DAC, 1), delay(10*us),
           ]
    if withTimer:
        seq.extend([INIT_TIMER, STOP_TIMER])
    if not loopForever:
        seq.append(END)
    return flatten(seq)
    
def triangleWave2(center=0*V, amplitude=1*V,
                    frequency=10*Hz, steps=30, loopForever=True,
                    withTimer=False, DAC=SQUID):
    """Generate a triangle waveform, suitable for looping."""
    steplen = (1/frequency) / 4 / steps
    
    voltages = linspace(center, center + amplitude, steps)\
             + linspace(center + amplitude, center - amplitude, steps*2)\
             + linspace(center - amplitude, center, steps)

    cmds = [[setDACvoltage2(DAC, 1, v), delay(steplen)] for v in voltages]
    seq = [START,
           #switchDAC(DAC, 1, slow=True), delay(10*us),
           cmds,
           #switchDAC(DAC, 1), delay(10*us),
           ]
    if withTimer:
        seq.extend([INIT_TIMER, STOP_TIMER])
    if not loopForever:
        seq.append(END)
    return flatten(seq)

def squidRampSeq(start, end, length=150*us, overshoot=0*V, DAC=SQUID):
    seq = [
        setDACvoltage(DAC, 1, start), delay(10*us),
        switchDAC(DAC, 1, slow=True), delay(10*us),

        INIT_TIMER,
        setDACvoltage(DAC, 1, end), delay(length),
        STOP_TIMER,

        switchDAC(DAC, 1), delay(10*us), # switch back to fast mode
        setDACvoltage(DAC, 1, overshoot), delay(10*us), # overshoot to help reset to zero state
        setDACvoltage(DAC, 1, 0*V), delay(10*us)
    ]
    return flatten(seq)
    
def squidRampSeq2(start, end, length=150*us, overshoot=0*V, DAC=SQUID):
    seq = [
        setDACvoltage2(DAC, 1, start), delay(100*us),

        INIT_TIMER,
        setDACvoltage2(DAC, 1, end, slow = True), delay(length),
        STOP_TIMER,

        setDACvoltage2(DAC, 1, overshoot), delay(10*us), # overshoot to help reset to zero state
        setDACvoltage2(DAC, 1, 0*V), delay(10*us)
    ]
    return flatten(seq)

def memWithSRAM(sram, qubitBias, measBias, reset,
                squidRamp, squidBias=0*V,
                qubitSettleTime=40*us,
                measureSettleTime=40*us,
                squidDAC=SQUID, fluxDAC=FLUX,
                preRampDelay=10*us, postRampDelay=10*us,
                master=True):
    if master:
        SRAMStartDelay = delay(25*us)
    else:
        SRAMStartDelay = []
    seq = [
        START,
        resetQubit(**reset),
        
        # set squid bias
        setDACvoltage(squidDAC, 1, squidBias), delay(10*us),
        switchDAC(squidDAC, 1), delay(10*us),

        # set qubit bias
        switchDAC(fluxDAC, 1), delay(10*us),
        setDACvoltage(fluxDAC, 1, qubitBias), delay(qubitSettleTime),

        # trigger SRS for microwaves and measure pulse
        SRAMStartDelay,
        callSRAM(sram), delay(10*us),

        # measure
        setDACvoltage(fluxDAC, 1, measBias), delay(measureSettleTime),
        setDACvoltage(squidDAC, 1, 0*V), delay(10*us),
        delay(preRampDelay),
        squidRampSeq(**squidRamp),
        delay(postRampDelay),

        # turn off flux bias
        setDACvoltage(fluxDAC, 1, 0*V), delay(10*us),

        END
    ]
    return flatten(seq)

def memNoSRAM(qubitBias, measBias, reset,
              squidRamp, squidBias=0*V,
              qubitSettleTime=40*us,
              measureSettleTime=40*us,
              squidDAC=SQUID, fluxDAC=FLUX):
    seq = [
        START,

        # set squid bias
        setDACvoltage(squidDAC, 1, squidBias), delay(10*us),
        switchDAC(squidDAC, 1), delay(10*us),

        # set qubit bias
        resetQubit(**reset),
        switchDAC(fluxDAC, 1), delay(10*us),
        setDACvoltage(fluxDAC, 1, qubitBias), delay(qubitSettleTime),

        # measure
        setDACvoltage(fluxDAC, 1, measBias), delay(measureSettleTime),
        squidRampSeq(**squidRamp),

        # turn off flux bias
        setDACvoltage(fluxDAC, 1, 0*V), delay(10*us),

        END
    ]
    return flatten(seq)

def squidSteps(fluxBias, resetBias,
               squidRamp, squidBias=0*V,
               fluxSettleTime=500*us,
               squidDAC=SQUID, fluxDAC=FLUX):
    seq = [
        START,

        # set squid bias
        setDACvoltage(squidDAC, 1, squidBias), delay(10*us),
        switchDAC(squidDAC, 1), delay(10*us),

        # reset qubit and go to flux bias
        resetQubit(resetBias),
        setDACvoltage(fluxDAC, 1, fluxBias), delay(fluxSettleTime),

        squidRampSeq(**squidRamp),

        # turn off flux bias
        setDACvoltage(fluxDAC, 1, 0*V), delay(10*us),
        END
    ]
    return flatten(seq)

def constMem(qubitBias, fluxDAC=FLUX):
    seq = [
        START,
        setDACvoltage2(fluxDAC, 1, qubitBias), delay(100*us),
        INIT_TIMER,
        STOP_TIMER,
        END
    ]
    return flatten(seq)
    
def resetMem(qubitBias, qubitReset=2.5, fluxDAC=FLUX):
    seq = [
        START,
        setDACvoltage2(fluxDAC, 1, qubitReset), delay(100*us),
        setDACvoltage2(fluxDAC, 1, qubitBias), delay(100*us),
        INIT_TIMER,
        STOP_TIMER,
        END
    ]
    return flatten(seq)
    
   
    
def squidSteps2(fluxBias, resetBias,
               squidRamp, squidBias=0*V,
               fluxSettleTime=500*us,
               squidDAC=SQUID, fluxDAC=FLUX):
    seq = [
        START,

        # set squid bias
        setDACvoltage2(squidDAC, 1, squidBias), delay(100*us),
        # switchDAC(squidDAC, 1), delay(10*us),

        # reset qubit and go to flux bias
        resetQubit2(resetBias),
        setDACvoltage2(fluxDAC, 1, fluxBias), delay(fluxSettleTime),

        squidRampSeq2(**squidRamp),

        # turn off flux bias
        setDACvoltage2(fluxDAC, 1, 0*V), delay(10*us),
        END
    ]
    return flatten(seq)