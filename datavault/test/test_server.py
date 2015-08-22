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
        new_system = self.new_context_store_datavault()
        self.context, self.store, self.datavault = new_system
        self.set_default_labrad_server_mocks(self.datavault)

    def tearDown(self):
        _empty_and_remove_dir(self.datadir)

    def new_context_store_datavault(self, context_name='test-context'):
        # A new context.
        context = MockContext(name=context_name)
        # Create a new sessions store connected to the root directory.
        store = SessionStore(self.datadir, self.hub)
        # Create a new server.
        datavault = server.DataVault(store)
        datavault.initServer()
        return context, store, datavault

    def create_simple_dataset(self, name='foo'):
        return self.datavault.new(
                self.context,
                'foo',
                [('x', 'ms') ,('y', 'Volt')],
                [('z', 'E', 'eV')])

    def create_extended_dataset(self, name='foo'):
        return self.datavault.new_ex(
                self.context,
                name,
                [('x', [2, 2], 'v', 'ms'), ('y', [1], 'i', '')],
                [('z', 'E',  [1, 2], 'c', 'eV')])

    def add_data_simple(self):
        # Add two rows of data.
        data = [(.1, .2, .3), (.4, .5, .6)]
        self.datavault.add(self.context, data)
        return data

    def add_data_extended(self):
        # Add two rows of data.
        data_row_1 = ([[.1, .5], [.5, .9]], 2, [[.1j, 2j]])
        data_row_2 = ([[.3, .4], [.4, .8]], 3, [[.3j, 5j]])
        data = [data_row_1, data_row_2]
        self.datavault.add_ex(self.context, data)
        return data

    def add_data_extended_transpose(self):
        # Add two rows of transposed data.
        x = [[[.1, .5], [.5, .9]], [[.3, .4], [.4, .8]]]
        y = [2, 3]
        z =  [[[.1j, 2j]], [[.3j, 5j]]]
        data = [[x[0], y[0], z[0]], [x[1], y[1], z[1]]]
        self.datavault.add_ex_t(self.context, [x, y, z])
        return data

    def add_one_parameter(self, name='Param 1', data='data 1'):
        self.datavault.add_parameter(self.context, name, data)
        return name, data

    def add_two_parameters(self):
        self.datavault.add_parameters(
                self.context, (('Param 2', 'data 2'), ('Param 3', 'data 3')))
        return (('Param 2', 'data 2'), ('Param 3', 'data 3'))

    def add_comment(self):
        self.datavault.add_comment(self.context, 'userfoo', 'comment')
        return 'userfoo', 'comment'

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
            self.assertArrayEqual(expected_var.shape, actual_var.shape, msg=msg)
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
            if not hasattr(expected_entry, '__len__'):
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
        # Check the new session has the listener.
        self.assertEqual(set([self.context.ID]), new_session.listeners)
        self.assertEqual(set([]), root_session.listeners)

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
        self.create_simple_dataset()
        # Add data.
        added_data = self.add_data_simple()

        # Check that the data is there.
        data = self.datavault.get(self.context)
        self.assertArrayEqual(added_data, data)
        # Check that listeners are added to the dataset.
        dataset = self.datavault.getDataset(self.context)
        self.assertEqual(set([self.context.ID]), dataset.listeners)
        # Check that no more data is there.
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

    def test_add_data_extended(self):
        self.datavault.initContext(self.context)
        self.create_extended_dataset()
        added_data = self.add_data_extended()

        # Check that the data is there.
        data = self.datavault.get_ex(self.context)
        self.assertDataRowEqual(added_data[0], data[0])
        self.assertDataRowEqual(added_data[1], data[1])
        # Check that listeners are added to the dataset.
        dataset = self.datavault.getDataset(self.context)
        self.assertEqual(set([self.context.ID]), dataset.listeners)

        more_data = self.datavault.get_ex(self.context)
        self.assertArrayEqual([], more_data)

        # Check that data can be fetched incrementally.
        row_1 = self.datavault.get_ex(self.context, limit=1, startOver=True)
        row_2 = self.datavault.get_ex(self.context, limit=1)
        self.assertDataRowEqual(added_data[0], row_1[0])
        self.assertDataRowEqual(added_data[1], row_2[0])

        # Check that the data can be fetched in transpose format.
        data_t = self.datavault.get_ex_t(self.context, startOver=True)
        expected_x = [added_data[0][0], added_data[1][0]]
        expected_y = [added_data[0][1], added_data[1][1]]
        expected_z =  [added_data[0][2], added_data[1][2]]
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
        self.create_extended_dataset()
        added_data = self.add_data_extended_transpose()

        # Check that the data is there as non-transposed data.
        data = self.datavault.get_ex(self.context)
        self.assertDataRowEqual(added_data[0], data[0])
        self.assertDataRowEqual(added_data[1], data[1])
        # Check that listeners are added to the dataset.
        dataset = self.datavault.getDataset(self.context)
        self.assertEqual(set([self.context.ID]), dataset.listeners)

        more_data = self.datavault.get_ex(self.context)
        self.assertArrayEqual([], more_data)

        # Check that data can be fetched incrementally.
        row_1 = self.datavault.get_ex(self.context, limit=1, startOver=True)
        row_2 = self.datavault.get_ex(self.context, limit=1)
        self.assertDataRowEqual(added_data[0], row_1[0])
        self.assertDataRowEqual(added_data[1], row_2[0])

        # Check that the data can be fetched in transpose format.
        data_t = self.datavault.get_ex_t(self.context, startOver=True)
        expected_x = [added_data[0][0], added_data[1][0]]
        expected_y = [added_data[0][1], added_data[1][1]]
        expected_z =  [added_data[0][2], added_data[1][2]]
        self.assertArrayEqual(expected_x, data_t[0])
        self.assertArrayEqual(expected_y, data_t[1])
        self.assertArrayEqual(expected_z, data_t[2])

        # Extended data format cannot be read as simple data.
        self.assertRaises(
                errors.DataVersionMismatchError,
                self.datavault.get,
                self.context)

    def test_add_one_parameter(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.create_extended_dataset()
        # There should be no parameters for a new datavault.
        self.assertEqual([], self.datavault.parameters(self.context))

        # Add a single parameter.
        self.add_one_parameter()

        self.assertEqual(['Param 1'], self.datavault.parameters(self.context))
        # Check that listeners are added to the dataset.
        dataset = self.datavault.getDataset(self.context)
        self.assertEqual(set([self.context.ID]), dataset.param_listeners)

        self.assertEqual(
                'data 1', self.datavault.get_parameter(self.context, 'Param 1'))

    def test_get_parameter_case_sensitivity(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.create_extended_dataset()

        # Add a one parameter
        name, data = self.add_one_parameter(name='PARAM 1')
        # By default get_parameter is case sensitive.
        self.assertRaises(
                errors.BadParameterError,
                self.datavault.get_parameter,
                self.context,
                'param 1')

        self.assertEqual(
                data,
                self.datavault.get_parameter(
                        self.context, 'PARAM 1', case_sensitive=False))

    def test_add_multiple_parameters(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.create_extended_dataset()

        # There should be no parameters for a new datavault.
        self.assertEqual([], self.datavault.parameters(self.context))

        # Add two parameters at the same time.
        added_params = self.add_two_parameters()

        added_names = [added_params[0][0], added_params[1][0]]
        added_data = [added_params[0][1], added_params[1][1]]

        actual_names = self.datavault.parameters(self.context)
        self.assertEqual(added_names, actual_names)
        data_0 = self.datavault.get_parameter(self.context, added_names[0])
        self.assertEqual(added_data[0], data_0)
        data_1 = self.datavault.get_parameter(self.context, added_names[1])
        self.assertEqual(added_data[1], data_1)

        self.assertEqual(
                added_params, self.datavault.get_parameters(self.context))

    def test_add_and_get_comment(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        self.create_extended_dataset()

        # There should be no comments for a new datavault.
        self.assertEqual([], self.datavault.get_comments(self.context))

        # Add a comment.
        user, comment = self.add_comment()

        # Get it back.
        comments = self.datavault.get_comments(self.context)
        # Check that listeners are added to the dataset.
        dataset = self.datavault.getDataset(self.context)
        self.assertEqual(set([self.context.ID]), dataset.comment_listeners)
        self.assertEqual(user, comments[0][2])
        self.assertEqual(comment, comments[0][1])

    def test_add_tags_and_get_tags(self):
        # Create the root session.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        path_1, name_1 = self.create_extended_dataset(name='root')
        # Add another directory and dataset.
        self.datavault.cd(self.context, path='first', create=True)
        path_2, name_2 = self.create_extended_dataset(name='foo')

        # Set tag 'root' on the root directory.
        # This uses the list specification for the path and dataset.
        self.datavault.update_tags(self.context, ['root'], path_1, [name_1])
        # Set tag '1' on the first directory and current dataset.
        # This uses the string specification for the path and dataset.
        self.datavault.update_tags(self.context, '1', path_2[1], name_2)
        # Set a tag on the current dataset and 'first' path.
        # Does not set anything on the dataset.
        self.datavault.update_tags(self.context, '2', path_2[1], datasets=None)

        # Get the tags for all the datasets
        _, dataset_tags = self.datavault.get_tags(
                self.context, [], datasets=[name_1, name_2])
        self.assertEqual(
                [('00001 - root', ['root']), ('00001 - foo', ['1'])],
                dataset_tags)
        # Get the tags for all the dirs
        dir_tags, _ = self.datavault.get_tags(
                self.context, ['', 'first'], [])
        self.assertEqual(
                [('', ['root']), ('first', ['1', '2'])], dir_tags)

        # Get the tags for root dir and dataset
        dir_tags, dataset_tags = self.datavault.get_tags(
                self.context, '', '00001 - root')
        self.assertEqual([('', ['root'])], dir_tags)
        self.assertEqual([('00001 - root', ['root'])], dataset_tags)

        # Get the tags for the 'first' dir and dataset
        dir_tags, dataset_tags = self.datavault.get_tags(
                self.context, 'first', '00001 - foo')
        self.assertEqual([('first', ['1', '2'])], dir_tags)
        self.assertEqual([('00001 - foo', ['1'])], dataset_tags)

    # This test could be split up for better failure encapsulation.
    def test_load_all(self):
        # Set up a slightly non-trivial system first.
        self.datavault.initContext(self.context)
        # Create a root dataset.
        path_1, name_1 = self.create_extended_dataset(name='root')
        # Add another directory and dataset.
        self.datavault.cd(self.context, path='first', create=True)
        path_2, name_2 = self.create_extended_dataset(name='foo')
        # Add some data.
        self.add_data_extended_transpose()
        # Add some parameters.
        self.add_two_parameters()
        # Add a comment.
        self.add_comment()
        # Add a tags.
        self.datavault.update_tags(self.context, ['root'], path_1, [name_1])

        # Keep a record of all we added to compare to later.
        expected_sessions = self.datavault.dump_existing_sessions(self.context)
        added_data = self.datavault.get_ex(self.context)
        added_params = self.datavault.parameters(self.context)
        added_param_vals = [
                self.datavault.get_parameter(self.context, name)
                for name in added_params]
        added_variables = self.datavault.variables(self.context)
        added_variables_ex = self.datavault.variables_ex(self.context)
        added_comments = self.datavault.get_comments(self.context)
        tagged_dirs, tagged_datasets = self.datavault.get_tags(
                self.context, '', name_1)

        # Delete the current variables
        del self.store
        del self.context

        new_context, _, new_datavault = self.new_context_store_datavault(
                context_name='new-context')
        new_datavault.initContext(new_context)

        new_datavault.initContext(new_context)
        # Check the expected entries are in the directory.
        self.assertEqual(
                (['first'], ['00001 - root']), new_datavault.dir(new_context))
        # Now to get the session store to be aware of the sessions, we have to
        # walk the directory structure. For some reason it thinks we start at
        # ['', 'first'], so we need to go back to the root first.
        # Should this be this way?
        new_datavault.cd(new_context, '')
        new_datavault.cd(new_context, 'first')

        self.assertEqual(
                expected_sessions,
                new_datavault.dump_existing_sessions(new_context))


        # Open up the dataset in "first".
        new_datavault.open(new_context, '00001 - foo')

        # Check the variables are all the same.
        new_variables = new_datavault.variables(new_context)
        new_variables_ex = new_datavault.variables_ex(new_context)
        self.assertArrayEqual(added_variables, new_variables)
        self.assertListOfVariablesEqual(
                added_variables_ex[0], new_variables_ex[0])
        self.assertListOfVariablesEqual(
                added_variables_ex[1], new_variables_ex[1])

        # Check the data is all there.
        new_data = new_datavault.get_ex(new_context)
        self.assertDataRowEqual(added_data[0], new_data[0])
        self.assertDataRowEqual(added_data[1], new_data[1])

        # Check the parameters are all there.
        new_params = new_datavault.parameters(new_context)
        new_param_vals = [
                new_datavault.get_parameter(new_context, name)
                for name in new_params]
        self.assertEqual(added_params, new_params)
        self.assertEqual(added_param_vals, new_param_vals)

        # Check the comments are all there.
        new_comments = new_datavault.get_comments(new_context)
        self.assertEqual(added_comments, new_comments)

        # Check the tags are all there.
        new_tagged_dirs, new_tagged_datasets = new_datavault.get_tags(
                new_context, '', name_1)
        self.assertEqual(tagged_dirs, new_tagged_dirs)
        self.assertEqual(tagged_datasets, new_tagged_datasets)


class DataVaultMultiHeadTest(unittest.TestCase):

    @mock.patch('twisted.internet.task.LoopingCall')
    def setUp(self, MockLoopingCall):
        self.datadir = _unique_dir_name()
        self.clock = task.Clock()
        self.hub = mock.MagicMock()

    def tearDown(self):
        _empty_and_remove_dir(self.datadir)

    def get_datavault(self):
        host = 'foo'
        port = 1
        password = 'password'
        store = SessionStore(self.datadir, self.hub)
        dv = server.DataVaultMultiHead(host, port, password, self.hub, store)
        self.set_up_mock_twisted_client(dv)
        return dv

    def set_up_mock_twisted_client(self, datavault):
        datavault.client = mock.MagicMock()
        datavault.onShutdown = mock.MagicMock()

    @mock.patch('twisted.internet.task.LoopingCall')
    def test_init(self, MockLoopingCall):
        mock_timer = mock.MagicMock()
        MockLoopingCall.return_value = mock_timer
        datavault = self.get_datavault()
        datavault.initServer()

        # Check the looping timer with ping function was added.
        MockLoopingCall.assert_called_with(datavault.keepalive)
        self.assertEqual(mock_timer, datavault.keepalive_timer)
        # Check the timer was started.
        mock_timer.start.assert_called_with(120)
        # Check that the shutdown was added.
        datavault.onShutdown.return_value.addBoth.assert_called_with(
                datavault.end_keepalive)

        self.assertTrue(datavault.alive)

    @mock.patch('twisted.internet.task.LoopingCall')
    def test_end_keepalive(self, MockLoopingCall):
        mock_timer = mock.MagicMock()
        MockLoopingCall.return_value = mock_timer
        datavault = self.get_datavault()
        datavault.initServer()
        datavault.end_keepalive()
        mock_timer.stop.assert_called_once_with()

    def test_keepalive(self):
        datavault = self.get_datavault()
        datavault.keepalive()
        datavault.client.manager.echo.assert_called_once_with('ping')

    def test_keepalive_with_thrown_exception(self):
        datavault = self.get_datavault()
        datavault.client.manager.echo.side_effect = Exception('Boom')
        # Keepalive should catch the exception.
        datavault.keepalive()
        datavault.client.manager.echo.assert_called_once_with('ping')

    def test_add_server(self):
        datavault = self.get_datavault()
        datavault.add_server(None, 'new host')
        self.hub.add_server.assert_called_once_with('new host', 1, 'password')

    def test_get_servers(self):
        datavault = self.get_datavault()
        server1 = mock.MagicMock()
        server1.host = 'one'
        server1.port = 1
        del server1.server
        server2 = mock.MagicMock()
        server2.host = 'two'
        server2.port = 2
        server2.server.alive = True

        self.hub.__iter__.return_value = [server1, server2]
        servers = datavault.get_servers(None)
        self.assertEquals([('one', 1, False), ('two', 2, True)], servers)

    def test_ping_managers(self):
        datavault = self.get_datavault()
        datavault.ping_managers(None)
        self.hub.ping.assert_called_once_with()

    def test_kick_managers(self):
        datavault = self.get_datavault()
        datavault.kick_managers(None, host_regex='foo', port=1)
        self.hub.kick.assert_called_once_with('foo', 1)

        self.hub.reset_mock()
        datavault.kick_managers(None, host_regex='foo')
        self.hub.kick.assert_called_once_with('foo', 0)

    def test_reconnect_managers(self):
        datavault = self.get_datavault()
        datavault.reconnect(None, host_regex='foo', port=1)
        self.hub.reconnect.assert_called_once_with('foo', 1)

        self.hub.reset_mock()
        datavault.reconnect(None, host_regex='foo')
        self.hub.reconnect.assert_called_once_with('foo', 0)

    def test_refresh_managers(self):
        datavault = self.get_datavault()
        datavault.refresh_managers(None)
        self.hub.refresh_managers.assert_called_once_with()

    def test_context_key(self):
        datavault = self.get_datavault()
        context = MockContext()
        key = datavault.contextKey(context)
        self.assertEqual(datavault, key.server)
        self.assertEqual(context.ID, key.context)

if __name__ == '__main__':
    pytest.main(['-v', __file__])
