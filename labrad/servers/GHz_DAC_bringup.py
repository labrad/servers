"""
Version Info
version = 3.0
server: ghz_fpgas
server version: 3.3.0
"""

# CHANGELOG:
#
# 2013 September 2013 - Daniel Sank
#
# Major code clean up and simplification
#
# 2011 November 4 - Jim Wenner
#
# Revised calls to ghz_fpga server to match v3.3.0 call signatures and outputs.
# Incorporating usage of new bringup functions. Revised print outputs. Added
# ability to bring up all devices on a board group.

from __future__ import with_statement

import random
import time

import labrad
from math import sin, pi

FPGA_SERVER = 'ghz_fpgas'
DACS = ['A','B']
NUM_TRIES = 2

def bringupReportMessage(dac, data):
    """Build a report string from bringup data
    
    data is a dictionary of bringup results that should be built as follows:
        resp = fpga.dac_bringup(...)
        data = dict(resp[i]) (i=0 for DAC A, i=1 for DAC B)
    """
    report = ''
    #LVDS
    report += '\r\n'.join(['DAC %s LVDS parameters:'%dac,
        '  SD: %d'%data['lvdsSD'],
        '  Check: %d - What is this?'%data['lvdsCheck'],
        '  Plot MSD:  ' + ''.join('_-'[i] for i in data['lvdsTiming'][1]),
        '  Plot MHD:  ' + ''.join('_-'[i] for i in data['lvdsTiming'][2]),
        '', ''])
    #FIFO
    report += '\r\n'.join(['DAC %s FIFO Parameters:' %dac,
        '  FIFO calibration succeeded after %d tries'%data['fifoTries'],
        ''])
    if data['fifoSuccess']:
        report += '\r\n'.join([\
            '  FIFO PHOF: %d'%data['fifoPHOF'],
            '  Clk polarity: %d' %data['fifoClockPolarity'],
            '  FIFO counter: %d (should be 3)'%data['fifoCounter'],
            '', ''])
    else:
        report += '\r\n'.join(['FIFO failure', '', ''])
    #BIST
    report += '\r\n'.join(['DAC %s BIST:' %dac,
        ' Success: %s'%str(data['bistSuccess']),
        '', ''])
    return report
    
def bringupBoard(fpga, board, printOutput=True, optimizeSD=False, sdVal=None,fullOutput=False):
    """Bringup a single FPGA board
    
    This is the main bringup routine. All other bringup routines should call
    this one.
    
    RETURNS
    (boardType, results, {'bist':bool, 'fifo':bool, 'lvds':bool})
    
    results maps DAC -> data where DAC is 'A' or 'B' and data is another dict
    that maps parameterName -> value. For a complete specifications of all
    parameterName,value pairs, see the documentation for dac_bringup setting
    in the GHz FPGA server.
    """
    fpga.select_device(board)
    
    if board in fpga.list_adcs():
        fpga.adc_bringup()
        if printOutput:
            print('')
            print('ADC bringup on %s complete.' %board)
            print('No feedback information available %s' %board)
        return ('ADC', None, {})
    
    elif board in fpga.list_dacs():
        if sdVal is None:
            resp = fpga.dac_bringup(optimizeSD)
        else:
            resp = fpga.dac_bringup(False, sdVal)
        results={}
        #pass/fail indicators, one entry per DAC, ie. DAC A and DAC B
        fifoOkay = []
        bistOkay = []
        lvdsOkay = []
        for dacdata in resp:
            dacDict = dict(dacdata)
            dac = dacDict.pop('dac')
            results[dac] = dacDict
            
            fifoOkay.append(dacDict['fifoSuccess'])
            bistOkay.append(dacDict['bistSuccess'])
            lvdsOkay.append(dacDict['lvdsSuccess'])
            
            if fullOutput:
                print(bringupReportMessage(dac, dacDict))
            
        if printOutput:
            if all(fifoOkay) and all(bistOkay):
                print('%s ok' %board)
                if not all(lvdsOkay):
                    print('but LVDS warning')
            else:
                print('%s ---Bringup Failure---' %board)
        
        return ('DAC', results, {'bist':all(bistOkay), 'fifo':all(fifoOkay),
                'lvds':all(lvdsOkay)})
    
    else:
        raise RuntimeError("Board type not recognized. Something BAD happened")
    
def bringupBoards(fpga, boards, noisy=False):
    """Bringup a list of boards and return the Bist/FIFO and lvds success for
    each one.
    
    TODO:
    Put in code to keep track of retries and report this to the user
    """
    successes = {}
    triesDict = {}
    for board in boards:
        if noisy:
            print 'bringing up %s' %board
        #Temporarily set a value to False so while loop will run at least once
        allOk = False
        tries = 0
        #Try to bring up the board until it succeeds or we exceed maximum
        #number of tries.
        while tries < NUM_TRIES and not allOk:
            tries += 1
            triesDict[board] = tries
            boardType, result, successDict = bringupBoard(fpga, board,
                                                          fullOutput=False,
                                                          printOutput=True)
            allOk = all(successDict.values())
            successes[board] = successDict
    failures = []
    for board in boards:
        #Warn the user if a board took more than one try to bring up.
        if triesDict[board]>1:
            print 'WARNING: Board %s took %d tries to succeed' %(board,triesDict[board])
        #If this board failed, add it to the list of failures
        if not all(successes[board].values()):
            failures.append(board)
    if not failures:
        print 'All boards successful!'
    else:
        print 'The following boards failed:'
        for board in failures:
            print board
    
def interactiveBringup(fpga, board):
    """
    """
    boardType,_,_ = bringupBoard(fpga, board,fullOutput=True)

    if boardType == 'DAC':
        ccset = 0
        while True:
            print
            print
            print 'Choose:'
            print
            print '  [1] : Output 0x0000s'
            print '  [2] : Output 0x1FFFs'
            print '  [3] : Output 0x2000s'
            print '  [4] : Output 0x3FFFs'
            print
            print '  [5] : Output 100MHz sine wave'
            print '  [6] : Output 200MHz sine wave'
            print '  [7] : Output 100MHz and 175MHz sine wave'
            print
            print '        Current Cross Controller Setting: %d' % ccset
            print '  [+] : Increase Cross Controller Adjustment by 1'
            print '  [-] : Decrease Cross Controller Adjustment by 1'
            print '  [*] : Increase Cross Controller Adjustment by 10'
            print '  [/] : Decrease Cross Controller Adjustment by 10'
            print
            print '  [I] : Reinitialize'
            print
            print '  [Q] : Quit'
    
            k = getChoice('1234567+-*/IQ')
    
            # run various debug sequences
            if k in '1234567':
                if k == '1': fpga.dac_debug_output(0xF0000000, 0, 0, 0)
                if k == '2': fpga.dac_debug_output(0xF7FFDFFF, 0x07FFDFFF, 0x07FFDFFF, 0x07FFDFFF)
                if k == '3': fpga.dac_debug_output(0xF8002000, 0x08002000, 0x08002000, 0x08002000)
                if k == '4': fpga.dac_debug_output(0xFFFFFFFF, 0x0FFFFFFF, 0x0FFFFFFF, 0x0FFFFFFF)
                
                def makeSines(freqs, T):
                    """Build sram sequence consisting of superposed sine waves."""
                    wave = [sum(sin(2*pi*t*f) for f in freqs) for t in range(T)]
                    sram = [(long(round(0x1FFF*y/len(freqs))) & 0x3FFF)*0x4001 for y in wave]
                    sram[0] = 0xF0000000 # add triggers at the beginning
                    return sram
                    
                if k == '5': fpga.dac_run_sram(makeSines([0.100], 40), True)    
                if k == '6': fpga.dac_run_sram(makeSines([0.200], 40), True)    
                if k == '7': fpga.dac_run_sram(makeSines([0.100, 0.175], 40), True)
                
                print 'running...'
                
            if k in '+-*/':
                if k == '+': ccset += 1
                if k == '-': ccset -= 1
                if k == '*': ccset += 10
                if k == '/': ccset -= 10
            
                if ccset > +63: ccset = +63
                if ccset < -63: ccset = -63
                fpga.dac_cross_controller('A', ccset)
                fpga.dac_cross_controller('B', ccset)
                
            if k == 'I': bringupBoard(fpga, board,fullOutput=True)
            if k == 'Q': break
    
# User interface utilities

def getChoice(keys):
    """Get a keypress from the user from the specified keys."""
    r = ''
    while not r or r not in keys:
        r = raw_input().upper()
    return r

def selectFromList(options, title):
    """Get a user-selected option
    
    Returns an element from options.
    """
    print
    print
    print 'Select %s:' % title
    print
    keys = {}
    for i, opt in enumerate(options):
        key = '%d' % (i+1)
        keys[key] = opt
        print '  [%s] : %s' % (key, opt)
    keys['A'] = 'All'
    print '  [A] : All'
    keys['Q'] = None
    print '  [Q] : Quit'
    
    k = getChoice(keys)
    
    return keys[k]

def selectBoardGroup(fpga):
    """Gets user selected board group"""
    groups = fpga.list_board_groups()
    group = selectFromList(groups, 'Board Group')
    return group

def doBringup():
    with labrad.connect() as cxn:
        fpga = cxn[FPGA_SERVER]
        group = selectBoardGroup(fpga)
        while True:
            if group is None:
                break
            else:
                boards = fpga.list_devices(group) \
                        if group in fpga.list_board_groups() \
                        else fpga.list_devices()
            boardSelect = selectFromList(boards, 'FPGA Board')
            if boardSelect is None:
                break
            elif boardSelect == 'All':
                bringupBoards(fpga,[board[1] for board in boards],noisy=True)
            else:
                board = boardSelect[1]
                interactiveBringup(fpga, board)

if __name__ == '__main__':
    doBringup()
