from __future__ import with_statement

import time
from msvcrt import getch, kbhit

import labrad

def runSequences():
    count = 20
    for i in range(count+1):
        data = [0xF0000000, 0x00000000]*i + [0, 0]*(count-i)
        fpga.dac_run_sram(data, True)
        time.sleep(0.5)


with labrad.connect() as cxn:
    fpga = cxn.ghz_fpgas()

    while True:
        l = fpga.list_devices()
        k = []
        print 'Select FPGA Board:'
        print
        for i, n in enumerate(l):
            print '  [%d] : %s' % (i+1,n)
            k += ['%d' % (i+1)]

        print '  [R] : Refresh List'
        print '  [Q] : Quit'

        input = []
        while kbhit():
            getch()

        
        r = ''
        while r not in (k + ['Q', 'R']):
            r = raw_input('Pick selection and press [Enter]:').upper()
            #old code: r = getch().upper()

        if r == 'Q':
            exit()

        elif r == 'R':
            fpga.refresh_devices()

        else:
            break

    board = l[k.index(r)][1]

    print
    print 'Connecting to %s...' % board
    fpga.select_device(board)

    print
    print 'Initializing PLL..'
    fpga.pll_init()

    running = True
    print

    while running:
        print 'Choose:'
        print
        print '  [1] : Output 1000 repeat test (should repeat every 4ns)'
        print '  [2] : Run increasing sequence of 10 once'
        print '  [3] : Run increasing sequence of 10 continuously'
        print '  [I] : Initialize PLL loop (needed after reflashing FPGA)'
        print '  [Q] : Quit'

        while kbhit():
            getch()

        r = ''
        while r not in ['1', '2', '3', 'Q', 'I']:
            r = getch().upper()

        if r == '1':
            fpga.dac_debug_output([0xF0000000, 0, 0, 0])
            print 'running...'

        if r == '2':
            print 'running...'
            runSequences()

        if r == '3':
            print 'running... (press any key to stop)'
            while not kbhit():
                runSequences()

        if r == 'I':
            fpga.pll_init()
            print 'ready'

        if r == 'Q':
            running = False

        print
        print
        print

    print 'done...'
