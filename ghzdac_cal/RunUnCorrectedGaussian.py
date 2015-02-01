from __future__ import with_statement

import labrad
from labrad import types as T
from math import exp, log

with labrad.connection() as cxn:

    cxn.anritsu_server.select_device(0)
    cxn.anritsu_server.frequency(T.Value(6,'GHz'))
    cxn.anritsu_server.amplitude(T.Value(2.7,'dBm'))

    cxn.dac_calibration.board('DR Lab FPGA 0')
    cxn.dac_calibration.frequency(T.Value(6,'GHz'))

    data = [0]*1000

    width = 8

    factor = log(2)/(width/2)**2

    print factor

    for t in range(-50,51,1):
        data[t+197] = 1.7*exp(-factor * t**2)

    I = [int(d*0x0FFF) for d in data]
    Q = [0]*1000

    print I

    trigger = [0,0,0,0] + [0xF0000000] + [0]*995

    sram = [(t | ((q & 0x3FFF) << 14) | (i & 0x3FFF)) for t, i, q in zip(trigger, I, Q)]

    cxn.ghz_dacs.select_device('DR Lab FPGA 0')
    cxn.ghz_dacs.run_sram(sram, True)
