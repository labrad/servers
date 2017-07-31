"""

This is intended to test fpgalib/jump_table.py

"""

import numpy as np
import pytest
import fpgalib.jump_table as jump_table


def test_end():
    end = jump_table.JumpEntry(259, 0, jump_table.END())
    data = end.as_bytes()
    assert list(data) == [3, 1, 0, 0, 0, 0, 7, 0]


def test_nop():
    nop = jump_table.JumpEntry(259, 0, jump_table.NOP())
    data = nop.as_bytes()
    assert list(data) == [3, 1, 0, 0, 0, 0, 5, 0]


def test_idle():
    with pytest.raises(ValueError):
        jump_table.JumpEntry(64, 0, jump_table.IDLE(-1)).as_bytes()
    with pytest.raises(ValueError):
        jump_table.JumpEntry(64, 0, jump_table.IDLE(2 ** 15)).as_bytes()
    data = jump_table.JumpEntry(64, 0, jump_table.IDLE(64)).as_bytes()
    assert data[6] >> 1 == 64
    assert data[7] == 0


def test_cycle():
    data = jump_table.JumpEntry(64, 259, jump_table.CYCLE(2, 1)).as_bytes()
    assert list(data) == [64, 0, 0, 3, 1, 0, 35, 1]
    

def test_jump():
    data = jump_table.JumpEntry(64, 259, jump_table.JUMP(2)).as_bytes()
    assert list(data) == [64, 0, 0, 3, 1, 0, 13, 2]


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


if __name__ == '__main__':
    pytest.main(['-v', __file__])