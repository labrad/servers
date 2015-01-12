import os

from twisted.internet import reactor

try:
    import numpy as np
    use_numpy = True
except ImportError, e:
    print e
    print "Numpy not imported.  The DataVault will operate, but will be slower."
    use_numpy = False

from .errors import BadDataError

PRECISION = 12 # digits of precision to use when saving data
DATA_FORMAT = '%%.%dG' % PRECISION
FILE_TIMEOUT = 60 # how long to keep datafiles open if not accessed
DATA_TIMEOUT = 300 # how long to keep data in memory if not accessed

class SelfClosingFile(object):
    """
    A container for a file object that closes the underlying file handle if not
    accessed within a specified timeout. Call this container to get the file handle.
    """
    def __init__(self, filename, mode, timeout=FILE_TIMEOUT, touch=True):
        self.filename = filename
        self.mode = mode
        self.timeout = timeout
        self.callbacks = []
        if touch:
            self.__call__()

    def __call__(self):
        if not hasattr(self, '_file'):
            self._file = open(self.filename, self.mode)
            self._fileTimeoutCall = reactor.callLater(self.timeout, self._fileTimeout)
        else:
            self._fileTimeoutCall.reset(self.timeout)
        return self._file

    def _fileTimeout(self):
        for callback in self.callbacks:
            callback(self)
        self._file.close()
        del self._file
        del self._fileTimeoutCall

    def size(self):
        return os.fstat(self().fileno()).st_size

    def onClose(self, callback):
        self.callbacks.append(callback)

class CsvListData(object):
    """
    Data backed by a csv-formatted file.

    Stores the entire contents of the file in memory as a list or numpy array
    """

    def __init__(self, filename, cols, file_timeout=FILE_TIMEOUT, data_timeout=DATA_TIMEOUT):
        self.filename = filename
        self._file = SelfClosingFile(filename, 'a+', timeout=file_timeout)
        self.cols = cols
        self.timeout = data_timeout

    @property
    def file(self):
        return self._file()

    @property
    def data(self):
        """Read data from file on demand.

        The data is scheduled to be cleared from memory unless accessed."""
        if not hasattr(self, '_data'):
            self._data = []
            self._datapos = 0
            self._timeout_call = reactor.callLater(self.timeout, self._on_timeout)
        else:
            self._timeout_call.reset(DATA_TIMEOUT)
        f = self.file
        f.seek(self._datapos)
        lines = f.readlines()
        self._data.extend([float(n) for n in line.split(',')] for line in lines)
        self._datapos = f.tell()
        return self._data

    def _on_timeout(self):
        del self._data
        del self._datapos
        del self._timeout_call

    def _saveData(self, data):
        f = self.file
        for row in data:
            # always save with dos linebreaks
            f.write(', '.join(DATA_FORMAT % v for v in row) + '\r\n')
        f.flush()

    def addData(self, data):
        if not len(data) or not isinstance(data[0], list):
            data = [data]
        if len(data[0]) != self.cols:
            raise BadDataError(self.cols, len(data[0]))

        # append the data to the file
        self._saveData(data)

    def getData(self, limit, start):
        if limit is None:
            data = self.data[start:]
        else:
            data = self.data[start:start+limit]
        return data, start + len(data)

    def hasMore(self, pos):
        return pos < len(self.data)

class CsvNumpyData(CsvListData):
    """
    Data backed by a csv-formatted file.

    Stores the entire contents of the file in memory as a list or numpy array
    """

    def __init__(self, filename, cols):
        self.filename = filename
        self._file = SelfClosingFile(filename, 'a+')
        self.cols = cols

    @property
    def file(self):
        return self._file()

    def _get_data(self):
        """Read data from file on demand.

        The data is scheduled to be cleared from memory unless accessed."""
        if not hasattr(self, '_data'):
            try:
                # if the file is empty, this line can barf in certain versions
                # of numpy.  Clearly, if the file does not exist on disk, this
                # will be the case.  Even if the file exists on disk, we must
                # check its size
                if self._file.size() > 0:
                    self._data = np.loadtxt(self.file, delimiter=',')
                else:
                    self._data = np.array([[]])
                if len(self._data.shape) == 1:
                    self._data.shape = (1, len(self._data))
            except ValueError:
                # no data saved yet
                # this error is raised by numpy <=1.2
                self._data = np.array([[]])
            except IOError:
                # no data saved yet
                # this error is raised by numpy 1.3
                self.file.seek(0)
                self._data = np.array([[]])
            self._timeout_call = reactor.callLater(DATA_TIMEOUT, self._on_timeout)
        else:
            self._timeout_call.reset(DATA_TIMEOUT)
        return self._data

    def _set_data(self, data):
        self._data = data

    data = property(_get_data, _set_data)

    def _on_timeout(self):
        del self._data
        del self._timeout_call

    def _saveData(self, data):
        f = self.file
        # always save with dos linebreaks (requires numpy 1.5.0 or greater)
        np.savetxt(f, data, fmt=DATA_FORMAT, delimiter=',', newline='\r\n')
        f.flush()

    def addData(self, data):
        data = np.asarray(data)

        # reshape single row
        if len(data.shape) == 1:
            data.shape = (1, data.size)

        # check row length
        if data.shape[-1] != self.cols:
            raise BadDataError(self.cols, data.shape[-1])

        # append data to in-memory data
        if self.data.size > 0:
            self.data = np.vstack((self.data, data))
        else:
            self.data = data

        # append data to file
        self._saveData(data)

    def getData(self, limit, start):
        if limit is None:
            data = self.data[start:]
        else:
            data = self.data[start:start+limit]
        # nrows should be zero for an empty row
        nrows = len(data) if data.size > 0 else 0
        return data, start + nrows

    def hasMore(self, pos):
        # cheesy hack: if pos == 0, we only need to check whether
        # the filesize is nonzero
        if pos == 0:
            return os.path.getsize(self.filename) > 0
        else:
            nrows = len(self.data) if self.data.size > 0 else 0
            return pos < nrows

def create_backend(filename, cols):
    """Make a data object that manages in-memory and on-disk storage for a dataset.

    filename should be specified without a file extension. If there is an existing
    file in csv format, we create a backend of the appropriate type. If
    no file exists, we create a new backend to store data in binary form.
    """
    csv_file = filename + '.csv'
    if os.path.exists(csv_file):
        if use_numpy:
            return CsvNumpyData(csv_file, cols)
        else:
            return CsvListData(csv_file, cols)
    else:
        if use_numpy:
            return CsvNumpyData(csv_file, cols)
        else:
            return CsvListData(csv_file, cols)
