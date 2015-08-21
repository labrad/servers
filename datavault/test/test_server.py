import mock
import numpy as np
import os
import pytest
import tempfile
import unittest

from twisted.internet import reactor, task

from labrad.server import LabradServer, Signal, setting
from labrad import server

from datavault import backend, errors, server, SessionStore


def _unique_dir():
    return tempfile.mkdtemp(prefix='dvtest_')


def _unique_dir_name():
    newdir = _unique_dir()
    # Remove the newly created directory as this wil be recreated by the
    # Session.
    _empty_and_remove_dir(newdir)
    return newdir


def _empty_and_remove_dir(*names):
    for name in names:
        if not os.path.exists(name):
            continue
        for listedname in os.listdir(name):
            path = os.path.join(name, listedname)
            if os.path.isdir(path):
                _empty_and_remove_dir(name + '/' + listedname)
            else:
                os.remove(path)
        os.rmdir(name)


class MockContext(dict):
    def __init__(self, name='test-context'):
        self.ID = name


class DataVaultTest(unittest.TestCase):
    '''Tests for the datavault server.'''

    def setUp(self):
        self.datadir = _unique_dir_name()
        self.hub = mock.MagicMock()
        self.store = SessionStore(self.datadir, self.hub)
        self.datavault = server.DataVault(self.store)
        self.set_default_labrad_server_mocks(self.datavault)

        self.context = MockContext()

        self.datavault.initServer()

    def tearDown(self):
        _empty_and_remove_dir(self.datadir)

    def assertArrayEqual(self, expected, actual, msg=None):
        if len(expected) == 0 and len(actual) == 0:
            return
        if msg is None:
            msg = 'Arrays not equal\nfirst:\n{}\nsecond:\n{}'.format(
                    expected, actual)
        self.assertTrue(np.array_equal(expected, actual), msg=msg)

    def assertListOfVariablesEqual(self, expected, actual):
        self.assertEqual(len(expected), len(actual))
        msg_template = (
                'Mismatch in varianles list at position {}:'
                '\nexpected:\n{}\nactual:\n{}')

        items = enumerate(zip(expected ,actual))
        for i, (expected_var, actual_var) in items:
            msg = msg_template.format(i, expected_var, actual_var)
            self.assertEqual(expected_var.label, actual_var.label, msg=msg)
            self.assertEqual(
                    expected_var.datatype, actual_var.datatype, msg=msg)
            self.assertEqual(expected_var.unit, actual_var.unit, msg=msg)
            self.assertEqual(expected_var.shape, actual_var.shape, msg=msg)
            if hasattr(expected_var, 'legend'):
                self.assertTrue(hasattr(actual_var, 'legend'), msg=msg)
                self.assertEqual(
                        expected_var.legend, actual_var.legend, msg=msg)


    def assertDataRowEqual(self, expected, actual):
        """Checks that data in the expected and actual rows are equal.

        This is useful for the extended data format since numpy's array_equal
        doens't do very well with oddly shaped data."""
        msg_foot = '\nExpected:\n{}\nActual:\n{}'.format(expected, actual)
        self.assertEqual(len(expected), len(actual), msg=msg_foot)

        comparables = zip(expected, actual)
        msg_head = 'Mismatch in entry {} of data.'
        for i, (expected_entry, actual_entry) in enumerate(comparables):
            msg = msg_head.format(i) + msg_foot
            if isinstance(expected_entry, (int, long, float, complex)):
                self.assertEqual(expected_entry, actual_entry, msg=msg)
            else:
                self.assertArrayEqual(expected_entry, actual_entry, msg=msg)

    def set_default_labrad_server_mocks(self, labrad_server):
        pass

    def test_init_context(self):
        self.datavault.initContext(self.context)
        current_session = self.datavault.getSession(self.context)
        self.assertEqual('', self.context['path'][0])
        self.assertTrue(self.context.ID, current_session.listeners)
        sessions_in_store = self.store.get_all()
        self.assertEqual(1, len(sessions_in_store))
        self.assertEqual(set([self.context.ID]), sessions_in_store[0].listeners)
        self.assertEqual(current_session, sessions_in_store[0])

    def test_create_new_simple_dataset(self):
        # Create the root session and a child session.
        self.datavault.initContext(self.context)
        # Create a dataset at root.
        path, name = self.datavault.new(
                self.context, 'foo', [('x', 'ms')], [('y', 'E', 'eV')])

        self.assertEqual([''], path)
        self.assertEqual('00001 - foo', name)
        self.assertEqual('2.0.0', self.datavault.get_version(self.context))

        # Check that it contains the right pieces.
        # Simple variables output.
        independents, dependents = self.datavault.variables(self.context)
        self.assertEqual([('x', 'ms')], independents)
        self.assertEqual([('y', 'E', 'eV')], dependents)

        # Extended variables output.
        independents_ex, dependents_ex = self.datavault.variables_ex(
                self.context)
        expected_independents_ex = [
                backend.Independent(
                    label='x', shape=(1,), datatype='v', unit='ms')]
        expected_dependents_ex = [
                backend.Dependent(
                    label='y', legend='E', shape=(1,), datatype='v', unit='eV')]

        self.assertEqual(expected_independents_ex, independents_ex)
        self.assertEqual(expected_dependents_ex, dependents_ex)

        # Name.
        self.assertEqual(name, self.datavault.get_name(self.context))
        # Row and transpose type.
        self.assertEqual('*(v[ms],v[eV])', self.datavault.row_type(self.context))
        self.assertEqual(
                '(*v[ms],*v[eV])', self.datavault.transpose_type(self.context))

    def test_expire_context(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.datavault.new(
                self.context, 'foo', [('x', 'ms')], [('y', 'E', 'eV')])
        dataset = self.datavault.getDataset(self.context)
        # Add the context as a listener to the dataset.
        dataset.listeners.add(self.context.ID)
        # Now expire the context
        self.datavault.expireContext(self.context)

        sessions_in_store = self.store.get_all()
        self.assertEqual(1, len(sessions_in_store))
        # Check the session doesn't have anymore listeners.
        self.assertEqual(set([]), sessions_in_store[0].listeners)
        # Check the dataset doesn't have anymore listeners.
        self.assertEqual(set([]), dataset.listeners)

    def test_get_dataset_not_yet_created(self):
        self.datavault.initContext(self.context)
        self.assertRaises(
                errors.NoDatasetError, self.datavault.getDataset, self.context)

    def test_add_session_with_cd(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        root_session = self.datavault.getSession(self.context)
        # Create another session.
        newpath = self.datavault.cd(self.context, path='first', create=True)
        new_session =  self.datavault.getSession(self.context)
        self.assertNotEqual(root_session, new_session)
        self.assertEqual(['', 'first'], newpath)

    def test_directory_operations(self):
        self.datavault.initContext(self.context)
        self.assertEqual(([], []), self.datavault.dir(self.context))
        # Create a new directory with a string.
        self.datavault.mkdir(self.context, 'first')
        # Check that we haven't changed the path yet.
        self.assertEqual([''], self.context['path'])
        # Check that the new directory is created.
        self.assertEqual((['first'], []), self.datavault.dir(self.context))

        # Change to the new directory.
        self.datavault.cd(self.context, path='first')
        self.assertEqual(['', 'first'], self.context['path'])
        # Check current directory is empty.
        self.assertEqual(([], []), self.datavault.dir(self.context))

        # Change to new directory, creating it as we go.
        self.datavault.cd(self.context, path=['second', 'third'], create=True)
        self.assertEqual(['', 'first', 'second', 'third'], self.context['path'])
        self.assertEqual(([], []), self.datavault.dir(self.context))

        # Change back to the root and traverse the path
        self.datavault.cd(self.context, path=[''])
        self.assertEqual((['first'], []), self.datavault.dir(self.context))
        self.datavault.cd(self.context, path=['first'])
        self.assertEqual((['second'], []), self.datavault.dir(self.context))
        self.datavault.cd(self.context, path=['second'])
        self.assertEqual((['third'], []), self.datavault.dir(self.context))
        self.datavault.cd(self.context, path=['third'])
        self.assertEqual(([], []), self.datavault.dir(self.context))

    def test_dump_existing_sessions(self):
        # Create the root session and a child session.
        self.datavault.initContext(self.context)
        self.datavault.cd(self.context, path='first', create=True)
        self.datavault.cd(self.context, path=['second', 'third'], create=True)
        all_sessions = self.datavault.dump_existing_sessions(self.context)
        self.assertEqual(['/first/second/third'], all_sessions)

    def test_add_simple_data(self):
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.datavault.new(
                self.context,
                'foo',
                [('x', 'ms'), ('y', 'Volt')],
                [('z', 'E', 'eV')])
        # Add two rows of data.
        self.datavault.add(self.context, [(.1, .2, .3), (.4, .5, .6)])
        # Check that the data is there.
        data = self.datavault.get(self.context)
        self.assertArrayEqual([[.1, .2, .3], [.4, .5, .6]], data)
        more_data = self.datavault.get(self.context)
        self.assertArrayEqual([], more_data)

        # Check that data can be fetched incrementally.
        row_1 = self.datavault.get(self.context, limit=1, startOver=True)
        row_2 = self.datavault.get(self.context, limit=1)
        self.assertArrayEqual([[.1, .2, .3]], row_1)
        self.assertArrayEqual([[.4, .5, .6]], row_2)

        # Check that the data can be fetched in extended format.
        data_ex = self.datavault.get_ex(self.context, startOver=True)
        self.assertArrayEqual([[.1, .2, .3], [.4, .5, .6]], data_ex)

        # Check that the data can not be fetched in extended transpose format.
        self.assertRaises(
                RuntimeError,
                self.datavault.get_ex_t,
                self.context,
                startOver=True)

    def test_add_extended_data(self):
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.datavault.new_ex(
                self.context,
                'foo',
                [('x', [2, 2], 'v', 'ms'), ('y', [1], 'i', '')],
                [('z', 'E',  [1, 2], 'c', 'eV')])
        # Add two rows of data.
        data_row_1 = ([[.1, .5], [.5, .9]], 2, [[.1j, 2j]])
        data_row_2 = ([[.3, .4], [.4, .8]], 3, [[.3j, 5j]])
        self.datavault.add_ex(self.context, [data_row_1, data_row_2])

        # Check that the data is there.
        data = self.datavault.get_ex(self.context)
        self.assertDataRowEqual(data_row_1, data[0])
        self.assertDataRowEqual(data_row_2, data[1])

        more_data = self.datavault.get_ex(self.context)
        self.assertArrayEqual([], more_data)

        # Check that data can be fetched incrementally.
        row_1 = self.datavault.get_ex(self.context, limit=1, startOver=True)
        row_2 = self.datavault.get_ex(self.context, limit=1)
        self.assertDataRowEqual(data_row_1, row_1[0])
        self.assertDataRowEqual(data_row_2, row_2[0])

        # Check that the data can be fetched in transpose format.
        data_t = self.datavault.get_ex_t(self.context, startOver=True)
        expected_x = [[[.1, .5], [.5, .9]], [[.3, .4], [.4, .8]]]
        expected_y = [2, 3]
        expected_z =  [[[.1j, 2j]], [[.3j, 5j]]]
        self.assertArrayEqual(expected_x, data_t[0])
        self.assertArrayEqual(expected_y, data_t[1])
        self.assertArrayEqual(expected_z, data_t[2])

        # Extended data format cannot be read as simple data.
        self.assertRaises(
                errors.DataVersionMismatchError,
                self.datavault.get,
                self.context)

    def test_add_extended_data_transpose(self):
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.datavault.new_ex(
                self.context,
                'foo',
                [('x', [2, 2], 'v', 'ms'), ('y', [1], 'i', '')],
                [('z', 'E',  [1, 2], 'c', 'eV')])
        # Add two rows of transposed data.
        x = [[[.1, .5], [.5, .9]], [[.3, .4], [.4, .8]]]
        y = [2, 3]
        z =  [[[.1j, 2j]], [[.3j, 5j]]]
        self.datavault.add_ex_t(self.context, [x, y, z])

        # Check that the data is there as non-transposed data.
        data_row_1 = ([[.1, .5], [.5, .9]], 2, [[.1j, 2j]])
        data_row_2 = ([[.3, .4], [.4, .8]], 3, [[.3j, 5j]])
        data = self.datavault.get_ex(self.context)
        self.assertDataRowEqual(data_row_1, data[0])
        self.assertDataRowEqual(data_row_2, data[1])

        more_data = self.datavault.get_ex(self.context)
        self.assertArrayEqual([], more_data)

        # Check that data can be fetched incrementally.
        row_1 = self.datavault.get_ex(self.context, limit=1, startOver=True)
        row_2 = self.datavault.get_ex(self.context, limit=1)
        self.assertDataRowEqual(data_row_1, row_1[0])
        self.assertDataRowEqual(data_row_2, row_2[0])

        # Check that the data can be fetched in transpose format.
        data_t = self.datavault.get_ex_t(self.context, startOver=True)
        self.assertArrayEqual(x, data_t[0])
        self.assertArrayEqual(y, data_t[1])
        self.assertArrayEqual(z, data_t[2])

        # Extended data format cannot be read as simple data.
        self.assertRaises(
                errors.DataVersionMismatchError,
                self.datavault.get,
                self.context)

if __name__ == '__main__':
    pytest.main(['-v', __file__])
