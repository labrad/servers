"""This is intended to test fpgalib/dac.py"""

import pytest
import numpy as np
import fpgalib.dac as dac


class TestDAC15(object):
    @classmethod
    def setup_class(cls):
        cls.dac = dac.DAC_Build15(0, 'dac_name')

        # sequence SRAM: pi pulse from 0-32, pi pulse from 32-64, ro from 64-400
        # experiment: first pi -> measure -> second pi -> measure -> end
        cls.first_pi_start = 0
        cls.first_pi_end = 32
        cls.second_pi_start = 32
        cls.second_pi_end = 64
        cls.ro_start = 64
        cls.ro_end = 400

        cls.jump_args = [
            ('JUMP', [cls.first_pi_end, cls.ro_start, 1]),
            ('JUMP', [cls.ro_end, cls.second_pi_start, 2]),
            ('END', [cls.ro_end])
        ]

    def make_entries(self, jump_args):
        return [self.dac.make_jump_table_entry(name, args)
                for name, args in jump_args]

    def test_make_jump_table_entry(self):
        _ = self.make_entries(self.jump_args)
        # we made it this far and we're feeling pretty good about it

    def test_make_jump_table(self):
        entries = self.make_entries(self.jump_args)
        self.dac.make_jump_table(entries)
        # we made it this far and we're feeling pretty good about it

    def test_catch_nop_nop_too_close(self):
        entries = self.make_entries([
            ('NOP', [16]),
            ('NOP', [20]),
            ('END', [400])
        ])
        with pytest.raises(ValueError):
            self.dac.make_jump_table(entries)

    def test_catch_jump_iterated_nop_too_close(self):

        entries = self.make_entries([
            ('JUMP', [32, 16, 1]),
            ('NOP', [20]),
            ('END', [400])
        ])
        with pytest.raises(ValueError):
            self.dac.make_jump_table(entries)

    def test_catch_jump_back_too_close(self):

        entries = self.make_entries([
            ('NOP', [32]),
            ('JUMP', [100, 28, 0]),
            ('END', [400])
        ])
        with pytest.raises(ValueError):
            self.dac.make_jump_table(entries)

    def test_catch_idle_end_too_close(self):

        # from addr of 32 is followed by from addr of 36 (even though IDLE?)
        entries = self.make_entries([
            ('IDLE', [32, 200]),
            ('END', [36])
        ])
        with pytest.raises(ValueError):
            self.dac.make_jump_table(entries)

    def test_nop_nop_1_clk_too_close(self):
        """Test a table that executes commands 1 clock cycle too frequently"""

        from_addr_ns = self.dac.JT_MIN_FROM_ADDR * 4
        entries = self.make_entries([
            ('NOP', [from_addr_ns]),
            ('NOP', [from_addr_ns +
                     (self.dac.JT_MIN_CLK_CYCLES_BETWEEN_OPCODES - 1) * 4]),
            ('END', [400])
        ])

        with pytest.raises(ValueError):
            self.dac.make_jump_table(entries)

    def test_nop_nop_min_clk_ok(self):
        from_addr_ns = self.dac.JT_MIN_FROM_ADDR * 4
        _ = self.make_entries([
            ('NOP', [from_addr_ns]),
            ('NOP', [from_addr_ns +
                     self.dac.JT_MIN_CLK_CYCLES_BETWEEN_OPCODES * 4]),
            ('END', [400])
        ])

    def test_max_entries(self):
        entry_sep = self.dac.JT_MIN_CLK_CYCLES_BETWEEN_OPCODES * 4 * 2
        from_addr = (entry_sep * np.arange(self.dac.JUMP_TABLE_COUNT - 2) +
                     entry_sep)
        entries = self.make_entries(
            [('NOP', [k]) for k in from_addr] +
            [('END', [from_addr[-1] + entry_sep])]
        )
        self.dac.make_jump_table(entries)
        # we made it this far and we're feeling pretty good about it

    def test_too_many_entries(self):
        entry_sep = self.dac.JT_MIN_CLK_CYCLES_BETWEEN_OPCODES * 4 * 2
        from_addr = (entry_sep * np.arange(self.dac.JUMP_TABLE_COUNT - 1) +
                     entry_sep)
        entries = self.make_entries(
            [('NOP', [k]) for k in from_addr] +
            [('END', [from_addr[-1] + entry_sep])]
        )
        with pytest.raises(ValueError):
            self.dac.make_jump_table(entries)

if __name__ == '__main__':
    pytest.main(['-v', __file__])
