"""

This is intended to test servers.GHzDACs.jumpTable.py

"""

import numpy as np
import pytest
import servers.GHzDACs.jump_table as jump_table


def test_limits():
    with pytest.raises(ValueError):
        jump_table.JumpEntry(-1, 0, jump_table.END())
    with pytest.raises(ValueError):
        jump_table.JumpEntry(9999, 0, jump_table.END())
    with pytest.raises(ValueError):
        jump_table.JumpEntry(10, -1, jump_table.END())
    with pytest.raises(ValueError):
        jump_table.JumpEntry(10, 9999, jump_table.END())


def test_end():
    end = jump_table.JumpEntry(259, 0, jump_table.END())
    data = end.as_bytes()
    assert data[0] == data[1] == 1
    assert data[2] == data[3] == data[4] == data[5] == 0
    assert data[6] == 7
    assert data[7] == 0


def test_nop():
    nop = jump_table.JumpEntry(259, 0, jump_table.NOP())
    data = nop.as_bytes()
    assert data[0] == 2
    assert data[1] == 1
    assert data[6] == 5
    assert data[7] == 0


def test_idle():
    with pytest.raises(ValueError):
        jump_table.JumpEntry(64, 0, jump_table.IDLE(0))
    with pytest.raises(ValueError):
        jump_table.JumpEntry(64, 0, jump_table.IDLE(2 ** 15))
    data = jump_table.JumpEntry(64, 0, jump_table.IDLE(64)).as_bytes()
    assert data[6] >> 1 == 63  # -1 for fpga offset
    assert data[7] == 0


def test_cycle():
    data = jump_table.JumpEntry(64, 259, jump_table.CYCLE(2, 1)).as_bytes()
    assert data[7] == 1
    assert data[6] == 35


def test_jump():
    data = jump_table.JumpEntry(64, 259, jump_table.JUMP(2)).as_bytes()
    assert data[3] == 3
    assert data[4] == 1
    assert data[5] == 0
    assert data[6] == 13
    assert data[7] == 2


@pytest.mark.skipif(True, reason="Ramp not implemented")
def test_ramp():
    pass


@pytest.mark.skipif(True, reason="Check not implemented")
def test_check():
    pass


def test_table():
    cycle = jump_table.JumpEntry(64, 0, jump_table.CYCLE(0, 1))
    end = jump_table.JumpEntry(80, 0, jump_table.END())
    jt = jump_table.JumpTable(32, [cycle, end], [259, 0, 0, 0])
    data = np.fromstring(jt.toString(), dtype='u1')
    # counters
    assert data[0] == 3
    assert data[1] == 1
    for i in range(2, 16):
        assert data[i] == 0
    # start addr
    assert data[16] == data[19] == 32
    for i in [17, 18, 20, 21, 23]:
        assert data[i] == 0
    # first JT must always be NOP
    assert data[22] == 5
    assert np.array_equal(data[24:32], cycle.as_bytes())
    assert np.array_equal(data[32:40], end.as_bytes())


def test_jt_run_sram():
    PERIOD = 2000  # as in IQ mixer calibration
    dataIn = np.zeros(PERIOD)
    # yield self._sendSRAM(data)
    startAddr, endAddr = 0, len(dataIn) // 4
    jt = jump_table.jt_run_sram(startAddr, endAddr, loop=True)
    jt_packet = np.fromstring(jt.toString(), dtype='u1')
    matching_jt = jump_table.JumpTable(start_addr=0, jumps=[jump_table.JumpEntry(PERIOD // 4, 0, jump_table.JUMP(1))])
    matching_jt_packet = np.fromstring(matching_jt.toString(), dtype='u1')
    assert np.array_equal(matching_jt_packet, jt_packet)

if __name__ == '__main__':
    pytest.main(['-v', __file__])