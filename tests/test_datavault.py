from datetime import datetime
import time

import numpy as np
import pytest

import labrad
import labrad.types as T
import labrad.util.hydrant as hydrant

# use the same path for all datasets in a given run of the tests in this module
_path = None

def _test_path():
    """Path where we'll put test datasets in the data vault"""
    global _path
    if _path is None:
        _path = ['test', datetime.utcnow().strftime('%Y%m%d')]
    return _path

def setup_dv(cxn):
    dv = cxn.data_vault
    dv.cd(_test_path(), True)
    return dv

@pytest.yield_fixture
def dv():
    with labrad.connect() as cxn:
        dv = setup_dv(cxn)
        yield dv

def test_create_dataset(dv):
    """Create a simple dataset, add some data and read it back"""
    _path, _name = dv.new('test', ['x', 'y'], ['z'])

    data = []
    for x in xrange(10):
        for y in xrange(10):
            data.append([x/10., y/10., x*y])

    for row in data:
        dv.add(row)

    stored = dv.get()
    assert dv.get_version() == "2.0.0"
    assert np.equal(data, stored).all()

def test_string_type(dv):
    _path, _name = dv.new_ex('test', [('label', [1], 's', '')],
                             [('data', 'data', [1], 's', '')])
    dv.add_ex([('label', 'data')])
    stored = dv.get_ex()
    assert stored[0][0] == 'label'
    assert stored[0][1] == 'data'
    stored = dv.get_ex_t()
    
def test_create_extended_dataset(dv):
    """Create an extended dataset, add some data and read it back"""
    _path, _name = dv.new_ex('test', [('t', [1], 'v', 'ns'),
                                      ('x', [2,2], 'c', 'V')],
                             [('clicks', 'I', [1], 'i', ''),
                              ('clicks', 'Q', [1], 'i', '')])

    t_data = 3.3
    x = np.array([[3.2+4j, 1.0],[15.8+11j, 2j]])
    I = 3
    Q = 7
    row  = (t_data, x, I, Q)
    dv.add_ex([row, row])
    dv.add_ex_t(([3.3, 3.3], np.array([x, x]), [3,3], [7,7]))
    
    dv.add_parameter('foo', 32.1)
    dv.add_parameter('bar', 'x')
    dv.add_parameter('baz', [1, 2, 3, 4])

    dv.open(_name)
    (indep_ex, dep_ex) = dv.variables_ex()
    assert len(indep_ex) == 2
    assert indep_ex[0] == ('t', [1], 'v', 'ns')
    assert indep_ex[1][0] == 'x'
    assert np.all(indep_ex[1][1] == [2,2])
    assert indep_ex[1][2:4] == ('c', 'V')
    assert len(dep_ex) == 2
    assert dep_ex[0] == ('clicks', 'I', [1], 'i', '')
    assert dep_ex[1] == ('clicks', 'Q', [1], 'i', '')
    
    (indep, dep) = dv.variables()
    assert indep[0] == ('t', 'ns')
    assert indep[1] == ('x', 'V')
    assert dep[0] == ('clicks', 'I', '')
    assert dep[1] == ('clicks', 'Q', '')

    row_type = dv.row_type()
    tt = T.parseTypeTag(row_type)
    assert tt == T.parseTypeTag('*(v[ns]*2c,ii)')

    assert dv.get_version() == "3.0.0"

    stored = dv.get_ex()
    for j in range(4):
        for k in range(4):
            assert np.all(stored[k][j] == row[j])

    stored = dv.get_ex_t(100, True)
    for j in range(4):
        for j in range(4):
            assert np.all(stored[j][k] == row[j])
    
def test_read_dataset():
    """Create a simple dataset and read it back while still open and after closed"""
    data = []
    for x in xrange(10):
        for y in xrange(10):
            data.append([x/10., y/10., x*y])

    with labrad.connect() as cxn:
        dv = setup_dv(cxn)

        path, name = dv.new('test', ['x', 'y'], ['z'])
        
        indep, dep = dv.variables()
        assert indep[0][0] == 'x'
        assert indep[1][0] == 'y'
        assert dep[0][0] == 'z'
        for row in data:
            dv.add(row)

        # read in new connection while the dataset is still open
        with labrad.connect() as cxn2:
            dv2 = cxn2.data_vault
            dv2.cd(path)
            dv2.open(name)
            stored = dv2.get()
            assert np.equal(data, stored).all()

            # add more data and ensure that we get it
            dv.add([1, 1, 100])

            row = dv2.get()
            assert np.equal(row, [1, 1, 100]).all()

    # read in new connection after dataset has been closed
    with labrad.connect() as cxn:
        dv = cxn.data_vault
        dv.cd(path)
        dv.open(name)
        stored = dv.get(len(data)) # get only up to the last extra row
        assert np.equal(data, stored).all()


def test_parameters(dv):
    """Create a dataset with parameters"""
    dv.new('test', ['x', 'y'], ['z'])
    for i in xrange(100):
        t = hydrant.randType(noneOkay=False)
        a = hydrant.randValue(t)
        name = 'param{}'.format(i)
        dv.add_parameter(name, a)
        b = dv.get_parameter(name)
        sa, ta = T.flatten(a)
        sb, tb = T.flatten(b)
        assert ta == tb
        assert sa == sb


# Test asynchronous notification signals.
# These signals are used by the grapher to do
# efficient UI updates without polling.

def test_signal_new_dir(dv):
    """Check messages sent when a new directory is created."""
    dirname = 'msg_test_dir' + str(time.time())

    msg_id = 123
    dv.signal__new_dir(msg_id)

    messages = []
    def on_message(ctx, msg):
        messages.append((ctx, msg))

    p = dv._cxn._backend.cxn
    p.addListener(on_message, source=dv.ID, ID=msg_id)

    dv.mkdir(dirname)
    time.sleep(0.5)

    assert len(messages) == 1

def test_signal_new_dataset(dv):
    """Check messages sent when a new dataset is created."""
    name = 'msg_test_dataset'

    msg_id = 123
    dv.signal__new_dataset(msg_id)

    messages = []
    def on_message(ctx, msg):
        messages.append((ctx, msg))

    p = dv._cxn._backend.cxn
    p.addListener(on_message, source=dv.ID, ID=msg_id)

    dv.new(name, ['x'], ['y'])
    time.sleep(0.5)

    assert len(messages) == 1

def test_signal_tags_updated(dv):
    """Check messages sent when tags on directories or datasets are updated."""
    dirname = 'msg_test_dir' + str(time.time())

    msg_id = 123
    dv.signal__tags_updated(msg_id)

    messages = []
    def on_message(ctx, msg):
        messages.append((ctx, msg))

    p = dv._cxn._backend.cxn
    p.addListener(on_message, source=dv.ID, ID=msg_id)

    dv.mkdir(dirname)
    dv.update_tags('test', [dirname], [])
    time.sleep(0.5)

    assert len(messages) == 1

def test_signal_data_available(dv):
    """Check that we get messages when new parameters are added to a data set."""
    msg_id = 123

    messages = []
    def on_message(ctx, msg):
        messages.append((ctx, msg))

    path, name = dv.new('test', ['x'], ['y'])

    # open a second connection which we'll use to read data added by the other
    with labrad.connect() as cxn:
        reader = setup_dv(cxn)
        reader.signal__data_available(msg_id)

        p = reader._cxn._backend.cxn
        p.addListener(on_message, source=reader.ID, ID=msg_id)

        reader.cd(path)
        reader.open(name)

        dv.add([1, 2])
        time.sleep(0.1)
        assert len(messages) == 1

        dv.add([3, 4])
        time.sleep(0.1)
        assert len(messages) == 1 # we should not get another message until we get the data

        data = reader.get()
        time.sleep(0.1)

        dv.add([5, 6])
        time.sleep(0.1)
        assert len(messages) == 2 # now we get a new message

def test_signal_new_parameter(dv):
    """Check messages sent when parameter is added to a dataset."""
    msg_id = 123

    messages = []
    def on_message(ctx, msg):
        messages.append((ctx, msg))

    path, name = dv.new('test', ['x'], ['y'])

    # open a second connection which we'll use to read params added by the other
    with labrad.connect() as cxn:
        reader = setup_dv(cxn)
        reader.signal__new_parameter(msg_id)

        p = reader._cxn._backend.cxn
        p.addListener(on_message, source=reader.ID, ID=msg_id)

        reader.cd(path)
        reader.open(name)

        reader.parameters() # get the list of parameters to signal our interest

        dv.add_parameter('a', 1)
        time.sleep(0.1)
        assert len(messages) == 1

        dv.add_parameter('b', 2)
        time.sleep(0.1)
        assert len(messages) == 1 # no new message until we get parameters

        params = reader.get_parameters()
        time.sleep(0.1)

        dv.add_parameters((('c', 3), ('d', 4)))
        time.sleep(0.1)
        assert len(messages) == 2 # just one message from multiple parameters


if __name__ == "__main__":
    pytest.main(['-v', __file__])
