"""

Attempt to test the GHz FPGA server.

Warning: too much of the functionality of the server is duplicated here.
For example, ``_fake_run_sequence`` emulates some of the logic in run_sequence()
and BoardGroup.run() rather than testing it.

A brief word on mocking:

The FPGA server we create here has its reference to the direct ethernet server
replaced by a mock.MagicMock object. This object records calls to it, and
returns other mock objects that record calls to them. So the loadPacket call
to the boardRunner class actually returns a mock object (received from the
call to the ``packet`` method fo the DE server), which has a record of calls
on _it_. We are interested in the ``write`` calls, so as to look at the data
being sent to the boards.

"""

import mock
import numpy as np
import pytest

import fpgalib.dac as dac
import fpgalib.fpga as fpga
import fpgalib.jump_table as jump_table
import ghz_fpga_server
from labrad.units import Value

NUM_DACS = 3
DAC_BUILD = 15

_JUMP_TABLE_IDLE_OFFSET = 0
_JUMP_TABLE_FROM_ADDR_OFFSET = -2
_JUMP_TABLE_END_ADDR_OFFSET = -3

class TestFPGAServer(object):

    @classmethod
    def setup_class(cls):
        cls.global_board_delay = 16
        cls.global_reps = 3000
        cls.server = ghz_fpga_server.FPGAServer()
        cls.ctx = cls.server.newContext(10)
        cls.server.initServer()
        cls.server.initContext(cls.ctx)
        cls._setup_devices()
        cls.server.select_device(cls.ctx, 1)

    @classmethod
    def _setup_devices(cls):
        dev_cls = fpga.REGISTRY[('DAC', 15)]
        for i in range(1, NUM_DACS + 1):
            dev = dev_cls(i, 'Test DAC {}'.format(i))
            dev.server = mock.MagicMock()
            dev.ctx = {}
            delay = (NUM_DACS - i) * 5  # TODO: account for this delay
            cls.server.devices[dev.guid] = dev
            cls.server.devices[dev.name] = dev
            if i == 1:
                cls.dev = dev  # store the first one for easy reference

    def setup_method(self, method):
        # reset the calls on the DE, for some reason mock hangs onto them.
        for dev in self.server.devices.values():
            dev.server = mock.MagicMock()

    def test_setup(self):
        assert(isinstance(self.dev, dac.DAC_Build15))
        assert(self.server.selectedDAC(self.ctx) is self.dev)

    def test_jt_run_sram(self):
        PERIOD = 2000  # as in IQ mixer calibration
        dataIn = np.zeros(PERIOD)
        startAddr, endAddr = 0, len(dataIn)
        jt = self.dev.jt_run_sram(startAddr, endAddr, loop=True)
        jt_packet = np.fromstring(jt.toString(), dtype='u1')
        entry = jump_table.JumpEntry(PERIOD // 4 + _JUMP_TABLE_FROM_ADDR_OFFSET,
                                     0, jump_table.JUMP(1))
        matching_jt = jump_table.JumpTable(start_addr=0, jumps=[entry])
        matching_jt_packet = np.fromstring(matching_jt.toString(), dtype='u1')
        assert np.array_equal(matching_jt_packet, jt_packet)

    def test_basic_run(self):
        sram_data = np.array(np.linspace(0, 0x3FFF, 256), dtype='<u4')
        matching_jt = jump_table.JumpTable(
            start_addr=0,
            # from_addr offset of -3 for END for this version of the JT
            jumps=[jump_table.JumpEntry(256//4 + _JUMP_TABLE_END_ADDR_OFFSET,
                                        0, jump_table.END())],
            counters=[0, 0, 0, 0]
        )
        matching_packet = np.fromstring(matching_jt.toString(), dtype='u1')

        s, c = self.server, self.ctx
        # do this board
        s.jump_table_clear(c)
        s.jump_table_add_entry(c, 'END', 256)
        s.dac_sram(c, sram_data)
        s.loop_delay(c, Value(50, 'us'))
        s.start_delay(c, 12)

        # global settings
        s.sequence_boards(c, [self.dev.name])  # actually the 'daisy_chain' setting
        s.sequence_timing_order(c, [])         # actually 'timing_order'

        self._fake_run_sequence()
        # check the run packet
        run_pkt = self.run_packets[0]
        assert run_pkt[0] == 1                                # master mode
        assert run_pkt[1] == 0                                # no readback
        assert run_pkt[13] == self.global_reps & 0xFF         # reps low byte
        assert run_pkt[14] == self.global_reps >> 8           # reps high byte
        assert run_pkt[15] == 50                              # loop delay
        assert run_pkt[16] == 0
        delay = 12 + self.global_board_delay + dac.MASTER_SRAM_DELAY_US
        assert run_pkt[43] == delay & 0xFF                    # delay
        assert run_pkt[44] == delay >> 8

        # check the SRAM and JT packets
        load_writes = self.load_writes[0]
        assert len(load_writes) == 2
        assert np.array_equal(load_writes[0], matching_packet)
        assert load_writes[1][0] == load_writes[1][1] == 0
        assert np.array_equal(load_writes[1][2:],
                              np.fromstring(sram_data.tostring(), dtype='u1'))

    def test_multiple_boards(self):
        loop_delay = Value(250, 'us')
        start_delays = [(NUM_DACS-i)*10 for i in range(NUM_DACS)]
        sram_data_1 = np.array(np.linspace(0, 0x3FFF, 512), dtype='<u4')
        sram_data_2 = np.array(np.ones_like(sram_data_1), dtype='<u4')
        matching_jt = jump_table.JumpTable(
            start_addr=0,
            jumps=[
                    jump_table.JumpEntry(
                            256//4 + _JUMP_TABLE_FROM_ADDR_OFFSET,
                            0,
                            jump_table.IDLE(1000//4 + _JUMP_TABLE_IDLE_OFFSET)),
                    jump_table.JumpEntry(
                            512//4 + _JUMP_TABLE_END_ADDR_OFFSET,
                            0,
                            jump_table.END())],
            counters=[0, 0, 0, 0]
        )
        matching_jt_packet = np.fromstring(matching_jt.toString(), dtype='u1')
        # set up the DACs
        s, c = self.server, self.ctx
        daisy_chain = []
        for i in range(1, NUM_DACS+1):
            s.select_device(c, i)
            s.jump_table_clear(c)
            s.jump_table_add_entry(c, 'IDLE', [256, 1000])
            s.jump_table_add_entry(c, 'END', 512)
            if i == 1:
                s.dac_sram(c, sram_data_1)
            else:
                s.dac_sram(c, sram_data_2)
            s.loop_delay(c, loop_delay)
            s.start_delay(c, start_delays[i-1])
            daisy_chain.append('Test DAC {}'.format(i))
        # global settings
        s.sequence_boards(c, daisy_chain)    # actually the 'daisy_chain' setting
        s.sequence_timing_order(c, [])         # actually 'timing_order'

        self._fake_run_sequence()

        for i in range(NUM_DACS):
            # check register packets
            p = self.run_packets[i]
            # first board is master
            if i == 0:
                assert p[0] == 1
            else:
                assert p[0] == 3
            packet_delay = p[43] + (p[44] >> 8)
            expected_delay = start_delays[i] + self.global_board_delay
            if i == 0:
                expected_delay += dac.MASTER_SRAM_DELAY_US
            assert packet_delay == expected_delay

            load_writes = self.load_writes[i]
            # check SRAM packets
            assert len(load_writes) == 3
            if i == 0:
                assert load_writes[1][2:].tostring() == sram_data_1[:256].tostring()
                assert load_writes[2][2:].tostring() == sram_data_1[256:].tostring()
            else:
                assert load_writes[1][2:].tostring() == sram_data_2[:256].tostring()
                assert load_writes[2][2:].tostring() == sram_data_2[256:].tostring()
            # check JT
            assert np.array_equal(matching_jt_packet, load_writes[0])

    def _fake_run_sequence(self):
        """ Emulate some of the logic of run_sequence for testing purposes.
        """
        s, c = self.server, self.ctx
        devs = [s.getDevice(c, name) for name in c['daisy_chain']]
        self.runners = [dev.buildRunner(self.global_reps, c.get(dev, {})) for dev in devs]
        self.load_packets, self.run_packets = [], []
        self.load_writes = []
        is_master = True
        for runner in self.runners:
            # TODO: sort by some board order and have only one be master
            p = runner.loadPacket(page=0, isMaster=is_master)
            self.load_packets.append(p)
            self.load_writes.append([
                np.fromstring(x[0][0], dtype='u1') for x in p.write.call_args_list
            ])
            self.run_packets.append(runner.runPacket(
                page=0, slave=int(not is_master), delay=self.global_board_delay, sync=249,
            ))
            is_master = False

if __name__ == '__main__':
    pytest.main(['-v', __file__])
