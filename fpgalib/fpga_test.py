"""Module for testing basic functionality of the FPGAs.

Getting Started
===============
To get started testing JT boards, see JumpTableTesting.md in the fpgalib/docs
folder.

This module interfaces with the boards _only_ through the ghz fpga server.

We have a suite of basic tests that are designed to exercise all of the
opcodes in the jump table, and verify that firmware-specific timing offsets
are accounted for correctly. These functions should all output a 100 ns long
step pulse. If the timing or opcodes are wrong, we should see a different
waveform. See:
*do_end
*do_nop
*do_idle
*do_jump
*do_cycle

How to use:
.. code:: python
  import labrad
  import fpgalib.fpga_test as ft
  cxn = labrad.connect()
  # For butterfly DAC 1
  tester = FPGATester(cxn.ghz_fpgas, 1, 'butterfly')
  tester.run_fpga_sequence(ft.do_end())  # play a test wave
  # Set the loop delay (delay between stats) to 20 us
  tester.register_config['loop_delay'] = 20
  # Set the monitors to show the register packet and the master start.
  # See fpgalib.dac for monitor definitions.
  tester.register_config['mon0'] = 0
  tester.register_config['mon1'] = 4
"""

import numpy as np
from fpgalib import fpga
import fpgalib.dac as dac
from labrad.units import Value


class FPGATester(object):
    """Class for testing a FPGA system with the Jump Table.

    Attributes:
        self.fpga (cxn.ghz_fpgas): The ghz fpga server.
        self.dac_num (int): The master DAC
        self.board_group_name (str): Board group name as identified in the
            registry.
        self.other_dac_nums (list[int]): List of slave DAC numbers (optional).
        self.adc_num (int): ADC number (optional).
        self.register_config (dict): This must be a list of keywords valid for
            dac.YOUR_DAC_BUILD.regrun.
        self.fpga (cxn.ghz_fpgas): The ghz fpga server.
    """

    def __init__(self, fpga, dac_num, board_group_name,
                 other_dac_nums=None, adc_num=None):
        """Create a new FPGATester.

        Args:
            fpga (cxn.ghz_fpgas): The ghz fpga server.
            dac_num (int): The master DAC
            board_group_name (str): Board group name as identified in the
                registry
            other_dac_nums (list[int]): List of slave DAC numbers (optional).
            adc_num (int): ADC number (optional).
        """

        self.fpga = fpga
        self.dac_num = dac_num
        self.board_group_name = board_group_name
        self.other_dac_nums = other_dac_nums if other_dac_nums else []
        self.adc_num = adc_num
        # default config kw args to dac.DAC_Build15.regRun
        self.register_config_default = {
            'reps': 30,
            'page': 0,
            'slave': 0,
            'delay': 0,
            'loop_delay': 0,
            'sync': 0,
            'monitor_0': 4,
            'monitor_1': 5
        }
        self.register_config = self.register_config_default.copy()

    def update_config(self, **kwargs):
        """Update the register packet configuration.

        Args:
            **kwargs (dict): Used to update self.registry_config
        """
        self.register_config.update(kwargs)

    def run_fpga_sequence(
            self,
            waveform_jtargs_counters,
            stats=30,
            adc_mon0=None,
            adc_mon1=None):
        """Run full FPGA sequence using the GHz FPGA server.

        Args:
            waveform_jtargs_counters:
            stats (int): Number of repetitions of the sequence.
            adc_mon0 (int): Setting for monitor 0 of the ADC
            adc_mon1 (int): Setting for monitor 1 of the ADC

        Returns: fpga.run_sequence
        """

        def name_board(dac_num, type='DAC'):
            return '{} {} {}'.format(self.board_group_name, type, dac_num)

        master_name = name_board(self.dac_num)
        slave_names = [name_board(dac_num)
                       for dac_num in self.other_dac_nums]
        waveform, jump_args, counters = waveform_jtargs_counters
        sram = np.array(dac.dacify(
                waveform,
                waveform,
                trigger_idx=[16,17]), dtype='<u4')

        for board in [master_name] + slave_names:
            self.fpga.select_device(board)
            self.fpga.jump_table_clear()
            for jump_arg in jump_args:
                opcode, arg = jump_arg
                self.fpga.jump_table_add_entry(opcode, arg)
            self.fpga.jump_table_set_counters(counters)
            self.fpga.sram(sram)
            self.fpga.start_delay(12)
            self.fpga.loop_delay(Value(50, 'us'))

        daisy = [master_name]

        if self.adc_num is not None:
            adc_name = name_board(self.adc_num, type='ADC')
            self.fpga.select_device(adc_name)
            self.fpga.adc_run_mode('demodulate')
            # Hard code begins here
            self.fpga.start_delay(4)
            self.fpga.adc_trigger_table([(1, 7, 40, 11)])
            mixer = 127*np.ones([512, 2])
            mixer[:, 1] *= 0
            self.fpga.adc_mixer_table(0, mixer)
            if adc_mon0 is not None:
                self.fpga.adc_monitor_outputs(adc_mon0, adc_mon1)

            self.fpga.timing_order([adc_name + '::0'])
            daisy.append(adc_name)
        else:
            self.fpga.timing_order([])

        for ob in slave_names:
            daisy.append(ob)
        self.fpga.daisy_chain(daisy)
        return self.fpga.run_sequence(stats, False)


# TEST FUNCTIONS

"""
See dac.DAC_Build15.make_jump_table_entry for jump_args syntax.
"""


def do_sine(end_time, build_number=15):
    """ Return SRAM and a JT for a sine wave of length end_time ns.

    Args:
        end_time (int): When to run END nop command
        build_number (int): Build number of the DAC, to look up in dac.py

    Returns (np.ndarray, list[tuple[str, args]], list[int]):
        SRAM data, arguments to construct the jump table, counters used in the
        jump table.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = 0.4 * np.sin(2 * np.pi / 256 * 8 * np.arange(256))

    jump_args = [
        ('END', end_time)
    ]

    counters = [0] * build_cls.NUM_COUNTERS

    return waveform, jump_args, counters


def do_end(end_time=160, build_number=15):
    """Test END function

    Args:
        end_time (int): When to run END nop command
        build_number (int): Build number of the DAC, to look up in dac.py

    Returns (np.ndarray, list[tuple[str, args]], list[int]):
        SRAM data, arguments to construct the jump table, counters used in the
        jump table.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[40:140] = 1.0
    waveform[160:256] = -1.0

    jump_args = [
        ('END', end_time)
    ]

    counters = [0] * build_cls.NUM_COUNTERS

    return waveform, jump_args, counters


def do_nop(build_number=15):
    """Test NOP function

    Args:
        build_number (int): Build number of the DAC, to look up in dac.py

    Returns (np.ndarray, list[tuple[str, args]], list[int]):
        SRAM data, arguments to construct the jump table, counters used in the
        jump table.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[40:140] = 1.0
    waveform[160:256] = -1.0

    jump_args = [
        ('NOP', 80),
        ('END', 160)
    ]

    counters = [0] * build_cls.NUM_COUNTERS

    return waveform, jump_args, counters


def do_idle(idle_time=96, build_number=15):
    """Test IDLE function

    Args:
        idle_time (int): Time in ns to idle for.
        build_number (int): Build number of the DAC, to look up in dac.py

    Returns (np.ndarray, list[tuple[str, args]], list[int]):
        SRAM data, arguments to construct the jump table, counters used in the
        jump table.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[40:44] = 1.0

    jump_args = [
        ('IDLE', (44, idle_time)),
        ('END', 256)
    ]

    counters = [0] * build_cls.NUM_COUNTERS

    return waveform, jump_args, counters


def do_jump(jump_time=60, build_number=15):
    """Test JUMP function

    Args:
        jump_time (int): When in ns to perform the JUMP command.
        build_number (int): Build number of the DAC, to look up in dac.py

    Returns (np.ndarray, list[tuple[str, args]], list[int]):
        SRAM data, arguments to construct the jump table, counters used in the
        jump table.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[40:100] = 1.0

    jump_args = [
        ('JUMP', (100, jump_time, 1)),
        ('END', 256)
    ]

    counters = [0] * build_cls.NUM_COUNTERS

    return waveform, jump_args, counters


def do_cycle(num_cycles=3, build_number=15):
    """Test CYCLE function

    We repeat 3 times so 100 ns = 24 * (3 + 1) + 4

    Args:
        num_cycles (int): Nunber of times to REPEAT sram.
        build_number (int): Build number of the DAC, to look up in dac.py

    Returns (np.ndarray, list[tuple[str, args]], list[int]):
        SRAM data, arguments to construct the jump table, counters used in the
        jump table.
    """
    build_cls = fpga.REGISTRY[('DAC', build_number)]

    waveform = np.zeros(256)
    waveform[40:68] = 1.0

    jump_args = [
        ('CYCLE', (64, 40, 0, 0)),
        ('END', 256)
    ]

    counters = [0] * build_cls.NUM_COUNTERS
    counters[0] = num_cycles

    return waveform, jump_args, counters
