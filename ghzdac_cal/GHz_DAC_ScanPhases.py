"""
Version Info
version = 1.0
server: ghz_fpgas
server version: 3.3.0
"""

# CHANGELOG:
#
# 2011 November 4 - Jim Wenner
#
# Revised calls to ghz_fpga server to match v3.3.0 call signatures and outputs.
# Incorporating usage of new bringup functions. Revised print outputs. Added
# ability to bring up all devices on a board group.

from __future__ import with_statement

import random
import time
import numpy as np
from scipy import optimize
import os
from math import sin, pi, ceil
from msvcrt import getch, kbhit
import labrad
from labrad.units import Unit,Value
import matplotlib.pyplot as plt

FPGA_SERVER='ghz_fpgas'
#TEK_SERVER='tektronix_5104b_oscilloscope' # Name of server for 1GHz oscilloscope
#TEK_SERVER='tektronix_7104b_oscilloscope' # Name of server for 1GHz oscilloscope
TEK_SERVER='agilent_7104b_oscilloscope'
DACS = ['A','B']
KEYS = ['lvdsMSD','lvdsMHD','lvdsSD','lvdsCheck','lvdsSuccess','fifoClockPolarity','fifoPHOF','fifoTries','fifoCounter','fifoSuccess','bistSuccess']

#LVDS parameters
#Refer to DAC chip datasheet page 40 of 72
#SD: Delay between data bus (DB<13:0>) and data clock (DATACLK_IN)
#Check: ?
#MSD: Measure Setup Delay
#MHD: Measure Hold Delay
# These should transition within one sample of each other. If they don't
# the DAC bringup script should give a warning.

#FIFO (First In First Out)
#Refer to DAC chip datasheet page 42 of 72
#The buffer is most stable if the read and write are approx half the buffer apart.
#FIFOSTAT<2:0> is exposed as FIFO counter in the bringup script. As per the datasheet
# this should be 3 or 4 indicating that read and write pointers are as far
# apart as possible.
#Clk Polarity: Polarity of some clock related to the FIFO buffer. The
# bringup script will flip this if it doesn't get a good (3 or 4)
# FIFO counter reading. It will keep flipping this (up to 5 tries)
# until a good count is achieved.

#BIST (Built In Self Test)
#Not sure what it does, but if it fails, you lose

#Results are saved in DIAGNOSTIC_ROOT

PLOT_FITS = False

# QuartusDirectory/quartus/bin must be in PATH environment variable
DIAGNOSTIC_ROOT = ['','Test','GHzFPGA']
NAME_PREFIX = 'FIFO3 SD'
SOF_DIR = 'U:/FPGAsof/GHzDAC_V56_B8'
#map clock phase -> sof file name
#First number is 250MHz FPGA clock. Increments of 22.5deg
#Second number is GHz clock. Incremments 45deg
SOF_FILES = {(0,90): 'GHzDAC_V5_B8_P90.sof',
             (0,135): 'GHzDAC_V5_B8_P135.sof',
             (0, 180): 'GHzDAC_V5_B8_P180.sof',
             (0,225): 'GHzDAC_V5_B8_P225.sof',
             (45,90): 'GHzDAC_V6_B8_P045_P090.sof',
             (45,135): 'GHzDAC_V6_B8_P045_P135.sof',
             (45, 180): 'GHzDAC_V6_B8_P045_P180.sof',
             (22,90): 'GHzDAC_V6_B8_P0225_P090.sof',
             (22,135):'GHzDAC_V6_B8_P0225_P135.sof',
             (22,180):'GHzDAC_V6_B8_P0225_P180.sof',
             }

def bringupBoard(fpga, board, printOutput=True, fullOutput=False, optimizeSD=False, sdVal=None):
    """Bringup a single board connected to the given fpga server."""
    fpga.select_device(board)
    
    # Determine if board is ADC. If so, bringup ADC.
    if board in fpga.list_adcs():
        fpga.adc_bringup()
        print ''
        print '%s ok' %board
        return ['ADC']
    
    if board in fpga.list_dacs():
        if sdVal is None:
            resp = fpga.dac_bringup(optimizeSD)
        else:
            resp = fpga.dac_bringup(False, sdVal)
        results={}
        okay = []
        lvdsOkay = []
        for dacdata in resp:
            dacdict=dict(dacdata)
            dac = dacdict.pop('dac')
            results[dac] = dacdict
            
            if printOutput:
                print ''
                print 'DAC %s LVDS Parameters:' % dac
                print '  SD: %d' % dacdict['lvdsSD']
                print '  Check: %d' % dacdict['lvdsCheck']
                print '  Plot MSD:  ' + ''.join('_-'[ind] for ind in dacdict['lvdsTiming'][1])
                print '  Plot MHD:  ' + ''.join('_-'[ind] for ind in dacdict['lvdsTiming'][2])
            lvdsOkay.append(dacdict['lvdsSuccess'])
            
            if printOutput:
                print ''
                print 'DAC %s FIFO Parameters:' % dac
                print '  FIFO calibration had to run %d times' %dacdict['fifoTries']
                if dacdict['fifoSuccess']:
                    print '  FIFO PHOF:   %d' % dacdict['fifoPHOF']
                    print '  Clk Polarity:  %d' % dacdict['fifoClockPolarity']
                    print '  FIFO Counter:  %d (should be 3)' %dacdict['fifoCounter']
                else:
                    print '  FIFO Failure!'
            okay.append(dacdict['fifoSuccess'])
            
            if printOutput:
                print ''
                print 'DAC %s BIST:' % dac
                print '  Success:' + yesNo(dacdict['bistSuccess'])
            okay.append(dacdict['bistSuccess'])
            
        print  ''
        if all(okay):
            print '%s ok' %board
            if not all(lvdsOkay):
                print 'LVDS warning'
        else:
            print '%s Bringup Failure!!! Reinitialize bringup!!!' %board
            
        if fullOutput:
            return ['DAC',results, all(okay), all(lvdsOkay)]
        else:
            return ['DAC']
    
def yesNo(booleanVal):
    if booleanVal:
        return 'Yes'
    elif (not booleanVal):
        return 'No'
    else:
        raise Exception
        
def clearscreen():
    os.system('cls')
    
def parseBringupOutput(data):
    if data[0] == 'DAC':
        parsed = []
        for dac in DACS:
            for key in KEYS:
                parsed.append(int(data[1][dac][key]))
        return parsed
    else:
        raise Exception('Did not select DAC board.')
    
def makeDACPulse(T):
    """Build sram sequence consisting of a square pulse (actually, Gaussian).
    """
    wave = np.zeros(T)
    wave[0:2]=1
    sram = [(long(round(0x1FFF*y)) & 0x3FFF)*0x4001 for y in wave]
    sram[0] = 0xF0000000 # add triggers at the beginning
    return sram
    
def prepScope(tek):
    print('Check that the following are connected.')
    print('Use equal length cables')
    print('   DAC A+ -> CH 1')
    print('   DAC B+ -> CH 2')
    print('   Trig S3+ -> CH 3')
    print('   MON 0 (fpga 250MHz clock) -> CH 4')
    _ = raw_input()
    #Scope parameters for 380mV amplitude sinewaves from diff amp
    for channel in [1,2]:
        tek.channelOnOff(channel,'ON')
        tek.invert(channel, 1)
        tek.termination(channel,50)
        tek.scale(channel, Value(100.0,'mV'))
        tek.position(channel,3)
        tek.coupling(channel, 'AC')
    #Scope parameters for trigger and FPGA clock
    for channel in [3,4]:
        tek.channelOnOff(channel,'ON')
        tek.invert(channel, 0)
        tek.termination(channel,50)
        tek.scale(channel, Value(500,'mV'))
        tek.position(channel,-3)
        tek.coupling(channel, 'AC')

    tek.trigger_slope('RISE')
    tek.trigger_level(Value(.750,'V'))
    tek.trigger_channel('CH4')
    
    horizPosition = 70
    horizScale = 4e-9
    tek.horiz_position(horizPosition)
    tek.horiz_scale(horizScale)
    
def measureScope(tek):
    """Measure DAC traces on scope and fit to determine horizontal positions.
    
    Note that we use Gaussians for the DAC A and B tests.
    We also bring out all traces with the x-axis in ns.
    """
    def gaussFunc(parm,z,time):
        """Gaussian function: y = c0 + c1 * exp(-(t-c2)^2/(2*c3^2))/sqrt(2*pi*c3)"""
        return abs(z - parm[0] - parm[1]*np.exp(-(time-parm[2])**2/(2*parm[3]**2))/np.sqrt(2*np.pi*parm[3]**2))
    def gauss2Func(parm,z,time):
        """Mexican hat function: y = c0 + c1 * exp(-(t-c2)^2/(2*c3^2))/sqrt(2*pi*c3) - c4 * exp(-(t-c2)^2/(2*c5^2))/sqrt(2*pi*c5)"""
        return abs(z - parm[0] - parm[1]*np.exp(-(time-parm[2])**2/(2*parm[3]**2))/np.sqrt(2*np.pi*parm[3]**2) + parm[4]*np.exp(-(time-parm[2])**2/(2*parm[5]**2))/np.sqrt(2*np.pi*parm[5]**2))
    
    if PLOT_FITS:
        plt.figure(42)
        plt.clf()
    try:
        timeAxis,voltAxis = tek.get_trace(1)
    except:
        print 'Ch1 not displayed'
        raise EOFError
    timeAxis_ns = np.array([tVal['ns'] for tVal in timeAxis])
    voltAxis_mV = np.array([yVal['mV'] for yVal in voltAxis])
    guess = np.array([0, -200, timeAxis_ns[np.argmin(voltAxis_mV)], 1])
    least1, error = optimize.leastsq(gaussFunc,guess,args=(voltAxis_mV, timeAxis_ns))
    if PLOT_FITS:
        print 'Ch1: ', timeAxis_ns[np.argmin(voltAxis_mV)]
        plt.plot(timeAxis_ns,voltAxis_mV,'y.')
        plt.plot(timeAxis_ns,least1[0] + least1[1]*np.exp(-(timeAxis_ns-least1[2])**2/(2*least1[3]**2))/np.sqrt(2*np.pi*least1[3]**2),'y')
        
    try:
        timeAxis,voltAxis = tek.get_trace(2)
    except:
        print 'Ch2 not displayed'
        raise EOFError
    timeAxis_ns = np.array([tVal['ns'] for tVal in timeAxis])
    voltAxis_mV = np.array([yVal['mV'] for yVal in voltAxis])
    guess = np.array([0, -200, timeAxis_ns[np.argmin(voltAxis_mV)], 1])
    least2, error = optimize.leastsq(gaussFunc,guess,args=(voltAxis_mV, timeAxis_ns))
    if PLOT_FITS:
        print 'Ch2: ', timeAxis_ns[np.argmin(voltAxis_mV)]
        plt.plot(timeAxis_ns,voltAxis_mV,'b.')
        plt.plot(timeAxis_ns,least2[0] + least2[1]*np.exp(-(timeAxis_ns-least2[2])**2/(2*least2[3]**2))/np.sqrt(2*np.pi*least2[3]**2),'b')
        
    try:
        timeAxis,voltAxis = tek.get_trace(4)
    except:
        print 'Ch4 not displayed'
        raise EOFError
    timeAxis_ns = np.array([tVal['ns'] for tVal in timeAxis])
    voltAxis_mV = np.array([yVal['mV'] for yVal in voltAxis])
    guess = np.array([20, 10000, timeAxis_ns[np.argmax(voltAxis_mV)], 1, 1000, 0.5])
    least4, error = optimize.leastsq(gauss2Func, guess, args=(voltAxis_mV, timeAxis_ns), maxfev=3000)
    if PLOT_FITS:
        print 'Ch4: ', timeAxis_ns[np.argmin(voltAxis_mV)]
        plt.plot(timeAxis_ns,voltAxis_mV,'g.')
        plt.plot(timeAxis_ns,least4[0] + least4[1]*np.exp(-(timeAxis_ns-least4[2])**2/(2*least4[3]**2))/np.sqrt(2*np.pi*least4[3]**2) - least4[4]*np.exp(-(timeAxis_ns-least4[2])**2/(2*least4[5]**2))/np.sqrt(2*np.pi*least4[5]**2),'g')
        
    try:
        timeAxis,voltAxis = tek.get_trace(3)
    except:
        print 'Ch3 not displayed'
        raise EOFError
    timeAxis_ns = np.array([tVal['ns'] for tVal in timeAxis])
    voltAxis_mV = np.array([yVal['mV'] for yVal in voltAxis])
    guess = np.array([1000, 1000, timeAxis_ns[np.argmax(voltAxis_mV)], 0.5])
    least3, error = optimize.leastsq(gaussFunc,guess,args=(voltAxis_mV, timeAxis_ns))
    if gaussFunc(least3, least3[0], least3[2])>250:
        found = True
    else:
        found = False
        least3[2]=least4[2]+1000
    if PLOT_FITS:
        print 'Ch3: ', timeAxis_ns[np.argmin(voltAxis_mV)]
        plt.plot(timeAxis_ns,voltAxis_mV,'m.')
        if found:
            plt.plot(timeAxis_ns,least3[0] + least3[1]*np.exp(-(timeAxis_ns-least3[2])**2/(2*least3[3]**2))/np.sqrt(2*np.pi*least3[3]**2),'m')
        plt.show()
            
    
    return [least1[2]-least4[2],least2[2]-least4[2],least3[2]-least4[2]]
        
def selectPhases():
    phases = sorted(SOF_FILES.keys())
    phases = selectItems(phases, 'Select for which phases to write SOF files to FPGA.')
    sofFiles = {}
    for phase in phases:
        sofFiles[phase] = SOF_FILES[phase]
    return sofFiles
    
def selectSDs():
    allSDs = ['Optimum']+range(16)
    sdsToMeasure = selectItems(allSDs, 'Select which LVDS SD values to measure')
    assert len(sdsToMeasure)!=0, "Must choose at least one SD to try"
    return sdsToMeasure
    
def singleParam(fpga, dv, tek, board, trials, name, optimizeSD, sdVal):
    #Set up dataset
    indeps = [('Trial','')]
    deps = []
    for dac in DACS:
        for key in KEYS:
            deps.append(('dac'+dac+' '+key, '', ''))
    deps = deps+[('Phase Error A','',''),
                 ('Phase Error B','',''),
                 ('Phase Error S','','')]
    dv.new(name,indeps,deps)
    # Run trials
    trial = 0
    while trial < trials:
        data = parseBringupOutput(bringupBoard(fpga, board, printOutput=False,
                                  fullOutput=True, optimizeSD=optimizeSD,
                                  sdVal=sdVal))
        fpga.dac_run_sram(makeDACPulse(40), True)
        try:
            data = data+measureScope(tek)
            dv.add([trial]+data)
        except EOFError:
            trials += 1
        trial += 1
    #Bring up board again to zero DAC outputs
    bringupBoard(fpga, board, printOutput=False)
    
def allParams(cxn, fpga, board, trials, dataDir, sds=None):
    """
    """
    dv = cxn.data_vault
    tek = cxn[TEK_SERVER]
    assert len(tek.list_devices())==1, "Not coded to handle multiple existing scopes"
    tek.select_device()
    prepScope(tek)

    sofFiles = selectPhases() #maps (FPGA phase, DAC phase) -> .sof file
    if sds is None:
        sds = selectSDs()
    for phase in sorted(sofFiles.keys()):
        #program FPGA with for this phase value
        oldDir = os.getcwd()
        os.chdir(SOF_DIR)
        if os.system('quartus_pgm -c EthernetBlasterII -m jtag -o p;'+SOF_FILES[phase]):
            os.chdir(oldDir)
            raise Exception('Programmer failed on '+str(phase))
        os.chdir(oldDir)
        time.sleep(15)
        #Set data vault directory
        dv.cd(DIAGNOSTIC_ROOT+[board]+[dataDir]+["%d_%d"%(phase[0],phase[1])],
              True)
        for sd in sds:
            if sd is 'Optimum':
                optimizeSD = True
                sdVal = None
                name = NAME_PREFIX+'Optimal'
            else:
                optimizeSD = False
                sdVal = sd
                name = NAME_PREFIX+str(sd)
            singleParam(fpga, dv, tek, board, trials, name, optimizeSD, sdVal)
    
### USER INTERFACE ###
    
def getChoice(keys):
    """Get a keypress from the user from the specified keys."""
    while kbhit():
        getch()
    r = ''
    while not r or r not in keys:
        r = raw_input().upper()
    return r
    
def selectItems(items, prompt):
    l = len(items)
    if l == 1:
        return items
#        return items[0]

    if l == 0:
        if returnIndex:
            return -1
        else:
            return []            
    
    while kbhit():
        getch()
    default = 0
    selection = []
    while True:
        clearscreen()
        print
        print prompt
        print '(SPACE to toggle, ESC to abort)'
        print
        for i, n in enumerate(items):
            if i == default:
                print '--> [%s] %s' % (' x'[i in selection], n)
            else:
                print '    [%s] %s' % (' x'[i in selection], n)
        r = getch()
        if r == '\x1b':
            return []
        elif r == '\r':
            selection.sort()
            return [items[i] for i in selection]
        elif r == ' ':
            if default in selection:
                selection.remove(default)
            else:
                selection.append(default)
        elif r == '\xe0':
            r = getch()
            if r == 'H':
                default -= 1
            elif r == 'P':
                default += 1
            default = default % l
    
def selectFromList(options, title):
    clearscreen()
    print 'Select %s:' % title
    print
    keys = {}
    for i, opt in enumerate(options):
        key = '%d' % (i+1)
        keys[key] = opt
        print '  [%s] : %s' % (key, opt)
    keys['Q'] = None
    print '  [Q] : Quit'
    k = getChoice(keys)
    return keys[k]
    
### Main routine ###
    
def doMultiBringup(trials=None, dataDir=None):
    if trials is None:
        raise RuntimeError("TODO: ")
    
    with labrad.connect() as cxn:
        fpga = cxn[FPGA_SERVER]
        boards = fpga.list_dacs()
        while True:
            board = selectFromList(boards, 'FPGA Board')
            if board is None:
                break
            else:
                allParams(cxn, fpga, board, trials, dataDir)
    
if __name__ == '__main__':
    doMultiBringup()
