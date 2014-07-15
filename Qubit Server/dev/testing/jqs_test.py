from __future__ import with_statement

import labrad
from labrad.units import GHz, dBm

singleQubit = {
        '0': {
            'meas': ('Analog', ['DR Lab FPGA 4', 'A']),
            'uwave': ('Iq', ['DR Lab FPGA 17']),
        },
        'trig': {
            'trig': ('Trigger', ['DR Lab FPGA 6', 'S0']),
        },
    }

twoQubits = {
        '0': {
            'timing': ('Preamp', ['DR Lab Preamp 1', 'A']),
            'flux': ('FastBias', ['DR Lab FastBias 2', 'A']),
            'squid': ('FastBias', ['DR Lab FastBias 3', 'A']),
            'meas': ('Analog', ['DR Lab FPGA 4', 'A']),
            'uwave': ('Iq', ['DR Lab FPGA 17']),
            'trig': ('Trigger', ['DR Lab FPGA 6', 'S0']),
        },
        '1': {
            'timing': ('Preamp', ['DR Lab Preamp 1', 'B']),
            'flux': ('FastBias', ['DR Lab FastBias 2', 'B']),
            'squid': ('FastBias', ['DR Lab FastBias 3', 'B']),
            'meas': ('Analog', ['DR Lab FPGA 4', 'B']),
            'uwave': ('Iq', ['DR Lab FPGA 6']),
            'trig': ('Trigger', ['DR Lab FPGA 6', 'S0']),
        },
        'trig': {
            'trig': ('Trigger', ['DR Lab FPGA 6', 'S0']),
        },
    }

twoQubitsWithRes = {
        '0': {
            'meas': ('Analog', ['DR Lab FPGA 4', 'A']),
            'uwave': ('Iq', ['DR Lab FPGA 17']),
            'timing': ('Preamp', ['DR Lab Preamp 1', 'A']),
            'squid': ('FastBias', ['DR Lab FastBias 2', 'A']),
            'flux': ('FastBias', ['DR Lab FastBias 3', 'A']),
        },
        '1': {
            'meas': ('Analog', ['DR Lab FPGA 4', 'B']),
            'uwave': ('Iq', ['DR Lab FPGA 6']),
            'timing': ('Preamp', ['DR Lab Preamp 1', 'B']),
            'squid': ('FastBias', ['DR Lab FastBias 2', 'B']),
            'flux': ('FastBias', ['DR Lab FastBias 3', 'B']),
        },
        'r': {
            'uwave': ('Iq', ['DR Lab FPGA 14']),
        },
        'trig': {
            'trig': ('Trigger', ['DR Lab FPGA 6', 'S0']),
        },
    }

# convert setups with dicts to for suitable for qubit server
flatten = lambda devs: [(n, list(ch.items())) for n, ch in devs.items()]

with labrad.connect() as cxn:
    qs = cxn.qubit_sequencer

    # test out a standard sequence
    # start a new sequence
    qs.initialize(flatten(twoQubits))

    # configure
    qs.new_config()
    for q in ['0', '1']:
        qs.config_microwaves(q, 6.5*GHz, 8.4*dBm)
        qs.config_preamp(q, 8453, True, '3300', '1')
        qs.config_settling(q, [1, 2, 3], [0.5, 0.1, 0.05])
    qs.config_timing_order(['0', '1'])
    # qs.config_timing_data (histogram, cutoffs/averages)
            
    # setup memory
    qs.new_mem()
    for block in ["ab", "ab'", "a'b", "a'b'"]:
        qs.mem_bias([(('0', 'flux'), 'dac1', 0),
                     (('0', 'squid'), 'dac1', 0),
                     (('1', 'flux'), 'dac1', 0),
                     (('1', 'squid'), 'dac1', 0)], 4.3)
        qs.mem_delay(10)
        qs.mem_call_sram(block)
        # measure q0
        qs.mem_start_timer(['0'])
        qs.mem_delay(10)
        qs.mem_stop_timer(['0'])
        # measure q1
        qs.mem_start_timer(['1'])
        qs.mem_delay(10)
        qs.mem_stop_timer(['1'])

    # setup sram
    for block in ["ab", "ab'", "a'b", "a'b'"]:
        qs.new_sram_block(block, 20)
        #qs.sram_trigger_pulses('trig', [(4,8)])
        for q in ['0', '1']:
            qs.sram_iq_data(q, [0] * 20)
            qs.sram_analog_data(q, [0] * 20)
        
    # go for it!
    qs.build_sequence(300L)
    a = qs.run()
    for s, d in a:
        print ('%s:' % s), d


    print
    print
    print


    # start a new sequence
    qubits = ['1', '2']
    qs.initialize(['qubit1', 'qubit2'], qubits)

    # configure
    qs.new_config()
    for q in qubits:
        qs.config_microwaves(q, 6.5*GHz, 8.4*dBm)
        qs.config_preamp(q, 8453, True, '3300', '1')
        qs.config_settling(q, [1,2,3], [0.5, 0.1, 0.05])
    qs.config_timing_order(['1', '2'])
    # qs.config_timing_data (histogram, cutoffs/averages)
            
    # setup memory
    qs.new_mem()
    for block in ["ab", "ab'", "a'b", "a'b'"]:
        qs.mem_bias([(('1', 'flux'), 'dac1', 0),
                     (('1', 'squid'), 'dac1', 0),
                     (('2', 'flux'), 'dac1', 0),
                     (('2', 'squid'), 'dac1', 0)], 4.3)
        qs.mem_delay(10)
        qs.mem_call_sram(block)
        # measure q0
        qs.mem_start_timer(['1'])
        qs.mem_delay(10)
        qs.mem_stop_timer(['1'])
        # measure q1
        qs.mem_start_timer(['2'])
        qs.mem_delay(10)
        qs.mem_stop_timer(['2'])

    # setup sram
    for block in ["ab", "ab'", "a'b", "a'b'"]:
        qs.new_sram_block(block, 20)
        #qs.sram_trigger_pulses('trig', [(4,8)])
        for q in qubits:
            qs.sram_iq_data(q, [0] * 20)
            qs.sram_analog_data(q, [0] * 20)
        
    # go for it!
    qs.build_sequence(300)
    a = qs.run()
    for s, d in a:
        print ('%s:' % s), d
        
        
    print
    print
    print


    # test out a dual-block sram sequence
    # start a new experiment
    qs.initialize(flatten(twoQubits))

    # configure
    qs.new_config()
    for q in ['0', '1']:
        qs.config_microwaves(q, 6.5*GHz, 8.4*dBm)
        qs.config_preamp(q, 8453, True, '3300', '1')
        qs.config_settling(q, [1,2,3], [0.5, 0.1, 0.05])
        # qs.config_timing_data (histogram, cutoffs/averages)
            
    # setup memory
    qs.new_mem()
    qs.mem_bias([(('0', 'flux'), 'dac1', 0),
                 (('0', 'squid'), 'dac1', 0),
                 (('1', 'flux'), 'dac1', 0),
                 (('1', 'squid'), 'dac1', 0)], 4.3)
    qs.mem_delay(10)
    qs.mem_call_sram('a', 'b', 5000)
    # measure q0
    qs.mem_start_timer(['0'])
    qs.mem_delay(10)
    qs.mem_stop_timer(['0'])
    # measure q1
    qs.mem_start_timer(['1'])
    qs.mem_delay(10)
    qs.mem_stop_timer(['1'])

    # setup sram
    for block in ['a', 'b']:
        qs.new_sram_block(block, 4)
        qs.sram_trigger_pulses('trig', [(0,1), (2,1)])
        for q in ['0', '1']:
            qs.sram_iq_data(q, [0, 0.25, 0.5, 0.75])
            qs.sram_analog_data(q, [0, 1, -1, 0])
    
    # go for it!
    qs.build_sequence(300)
    a = qs.run()
    for s, d in a:
        print ('%s:' % s), d


    print
    print
    print


    p = cxn.qubit_server.packet()

    # test out a standard sequence
    # start a new sequence
    qubits = ['0', '1']
    p.initialize(flatten(twoQubits))

    # configure
    p.new_config()
    for q in qubits:
        p.config_microwaves(q, 6.5*GHz, 8.4*dBm)
        p.config_preamp(q, 8453L, True, '3300', '1')
        p.config_settling(q, [1,2,3], [0.5, 0.1, 0.05])
    p.config_timing_order(qubits)
    # p.config_timing_data (histogram, cutoffs/averages)
            
    # setup memory
    p.new_mem()
    for block in ["ab", "ab'", "a'b", "a'b'"]:
        # initialize the flux and squid bias
        p.mem_bias([((q, 'flux'), 'dac1', 0) for q in qubits], 4.3)
        p.mem_bias([((qubits[0], 'flux'), 'dac1', 0),
                    ((qubits[0], 'squid'), 'dac1', 0),
                    ((qubits[1], 'flux'), 'dac1', 0),
                    ((qubits[1], 'squid'), 'dac1', 0)])
        p.mem_delay(10)
        p.mem_call_sram(block)
        # measure q0
        p.mem_start_timer([qubits[0]])
        p.mem_delay(10)
        p.mem_stop_timer([qubits[0]])
        # measure q1
        p.mem_start_timer([qubits[1]])
        p.mem_delay(10)
        p.mem_stop_timer([qubits[1]])

    # setup sram
    for block in ["ab", "ab'", "a'b", "a'b'"]:
        p.new_sram_block(block, 20L)
        #p.sram_trigger_pulses('trig', [(4,8)])
        for q in qubits:
            p.sram_iq_data(q, [0] * 20)
            p.sram_analog_data(q, [0] * 20)
        
    p.send()
        
    # go for it!
    p = cxn.qubit_server.packet()
    p.build_sequence(300)
    p.run(key='data')
    count = 0
    import time
    start = time.time()
    while 1:
        try:
            ans = p.send()
            count += 1
        except KeyboardInterrupt:
            elapsed = time.time() - start
            print 'elapsed=%g  iterations=%d  average=%g' % (elapsed, count, elapsed/count)
            exit()

    for s, d in ans['data']:
        print ('%s:' % s), d
