import StringIO
import pytest
import unittest

import numpy as np

from datavault import util

class Testutil(unittest.TestCase):
    @classmethod
    def setup_class(cls):
        pass

    def setup_method(self, method):
        pass

    def test_DVSafeConfigParser(self):
        parser = util.DVSafeConfigParser()
        parser.add_section('foo')
        parser.set('foo', 'alpha', '1')
        parser.set('foo', 'beta', '2')
        string_file = StringIO.StringIO()
        parser.write(string_file, '$$$')
        actual = string_file.getvalue()
        expected = '[foo]$$$alpha = 1$$$beta = 2$$$$$$'
        self.assertEqual(
                expected, actual, msg=('DVSafeConfigParser not writing with '
                                       'custom line ending'))

    def test_to_record_array(self):
        data = np.array([[0, 1, 2], [3, 4, 5]], dtype=complex)
        actual = util.to_record_array(data)
        expected = np.recarray(
            (2, ),
            dtype=[('f0', '<c16'), ('f1', '<c16'), ('f2', '<c16')])
        expected[0] = (0, 1, 2)
        expected[1] = (3, 4, 5)
        self.assertEqual(expected.shape, actual.shape, msg='shape mismatch')
        self.assertEqual(expected.dtype, actual.dtype, msg='dtype mismatch')
        self.assertTrue(np.array_equal(expected, actual), msg='array mismatch')

    def test_from_record_array(self):
        data = np.recarray(
            (2, ),
            dtype=[('f0', '<c16'), ('f1', '<c16'), ('f2', '<c16')])
        data[0] = (0, 1, 2)
        data[1] = (3, 4, 5)
        actual = util.from_record_array(data)
        expected = np.array([[0, 1, 2], [3, 4, 5]], dtype=complex)
        self.assertEqual(expected.shape, actual.shape, msg='shape mismatch')
        self.assertEqual(expected.dtype, actual.dtype, msg='dtype mismatch')
        self.assertTrue(np.array_equal(expected, actual), msg='array mismatch')

    def test_braced(self):
        actual = util.braced('foo')
        expected = '{' + 'foo' + '}'
        self.assertEqual(expected, actual)

if __name__ == '__main__':
    pytest.main(['-v', __file__])
