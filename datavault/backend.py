import os
import base64
import datetime
from twisted.internet import reactor

try:
    import numpy as np
    use_numpy = True
except ImportError, e:
    print e
    print "Numpy not imported.  The DataVault will operate, but will be slower."
    use_numpy = False
from labrad import types as T
from . import errors, util

TIME_FORMAT = '%Y-%m-%d, %H:%M:%S'
PRECISION = 12 # digits of precision to use when saving data
DATA_FORMAT = '%%.%dG' % PRECISION
FILE_TIMEOUT = 60 # how long to keep datafiles open if not accessed
DATA_TIMEOUT = 300 # how long to keep data in memory if not accessed
DATA_URL_PREFIX = 'data:application/labrad;base64,'

def time_to_str(t):
    return t.strftime(TIME_FORMAT)

def time_from_str(s):
    return datetime.datetime.strptime(s, TIME_FORMAT)

class SelfClosingFile(object):
    """
    A container for a file object that closes the underlying file handle if not
    accessed within a specified timeout. Call this container to get the file handle.
    """
    def __init__(self, opener=open, open_args=(), open_kw={}, timeout=FILE_TIMEOUT, touch=True):
        self.opener = opener
        self.open_args = open_args
        self.open_kw = open_kw
        self.timeout = timeout
        self.callbacks = []
        if touch:
            self.__call__()

    def __call__(self):
        if not hasattr(self, '_file'):
            self._file = self.opener(*self.open_args, **self.open_kw)
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

class IniData(object):
    """
    Handles dataset metadata stored in INI files.  

    This is used via subclassing mostly out of laziness: this was the
    easy way to separate it from the code that messes with the acutal
    data storage so that the data storage can be modified to use HDF5
    and complex data structures.  Once the HDF5 stuff is finished,
    this can be changed to use composition rather than inheritance.
    This provides the load() and save() methods to read and write the
    INI file as well as accessors for all the metadata attributes.
    """
    def load(self):
        S = util.DVSafeConfigParser()
        S.read(self.infofile)

        gen = 'General'
        self.title = S.get(gen, 'Title', raw=True)
        self.created = time_from_str(S.get(gen, 'Created'))
        self.accessed = time_from_str(S.get(gen, 'Accessed'))
        self.modified = time_from_str(S.get(gen, 'Modified'))

        def getInd(i):
            sec = 'Independent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            return dict(label=label, units=units)
        count = S.getint(gen, 'Independent')
        self.independents = [getInd(i) for i in range(count)]

        def getDep(i):
            sec = 'Dependent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            categ = S.get(sec, 'Category', raw=True)
            return dict(label=label, units=units, category=categ)
        count = S.getint(gen, 'Dependent')
        self.dependents = [getDep(i) for i in range(count)]
        
        self.cols = len(self.independents + self.dependents)

        def getPar(i):
            sec = 'Parameter %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            raw = S.get(sec, 'Data', raw=True)
            if raw.startswith(DATA_URL_PREFIX):
                # decode parameter data from dataurl
                all_bytes = base64.urlsafe_b64decode(raw[len(DATA_URL_PREFIX):])
                t, data_bytes = T.unflatten(all_bytes, 'ss')
                data = T.unflatten(data_bytes, t)
            else:
                # old parameters may have been saved using repr
                data = T.evalLRData(raw)
            return dict(label=label, data=data)
        count = S.getint(gen, 'Parameters')
        self.parameters = [getPar(i) for i in range(count)]

        # get comments if they're there
        if S.has_section('Comments'):
            def getComment(i):
                sec = 'Comments'
                time, user, comment = eval(S.get(sec, 'c%d' % i, raw=True))
                return time_from_str(time), user, comment
            count = S.getint(gen, 'Comments')
            self.comments = [getComment(i) for i in range(count)]
        else:
            self.comments = []

    def save(self):
        S = util.DVSafeConfigParser()

        sec = 'General'
        S.add_section(sec)
        S.set(sec, 'Created',  time_to_str(self.created))
        S.set(sec, 'Accessed', time_to_str(self.accessed))
        S.set(sec, 'Modified', time_to_str(self.modified))
        S.set(sec, 'Title',       self.title)
        S.set(sec, 'Independent', repr(len(self.independents)))
        S.set(sec, 'Dependent',   repr(len(self.dependents)))
        S.set(sec, 'Parameters',  repr(len(self.parameters)))
        S.set(sec, 'Comments',    repr(len(self.comments)))

        for i, ind in enumerate(self.independents):
            sec = 'Independent %d' % (i+1)
            S.add_section(sec)
            S.set(sec, 'Label', ind['label'])
            S.set(sec, 'Units', ind['units'])

        for i, dep in enumerate(self.dependents):
            sec = 'Dependent %d' % (i+1)
            S.add_section(sec)
            S.set(sec, 'Label',    dep['label'])
            S.set(sec, 'Units',    dep['units'])
            S.set(sec, 'Category', dep['category'])

        for i, par in enumerate(self.parameters):
            sec = 'Parameter %d' % (i+1)
            S.add_section(sec)
            S.set(sec, 'Label', par['label'])
            # encode the parameter value as a data-url
            data_bytes, t = T.flatten(par['data'])
            all_bytes, _ = T.flatten((str(t), data_bytes), 'ss')
            data_url = DATA_URL_PREFIX + base64.urlsafe_b64encode(all_bytes)
            S.set(sec, 'Data', data_url)

        sec = 'Comments'
        S.add_section(sec)
        for i, (time, user, comment) in enumerate(self.comments):
            time = time_to_str(time)
            S.set(sec, 'c%d' % i, repr((time, user, comment)))

        with open(self.infofile, 'w') as f:
            S.write(f)

    def initialize_info(self, title, indep, dep):
        self.title = title
        self.accessed = self.modified = self.created = datetime.datetime.now()
        self.independents = indep
        self.dependents = dep
        self.parameters = []
        self.comments = []
        self.cols = len(indep) + len(dep)

    def access(self):
        self.accessed = datetime.datetime.now()

    def getIndependents(self):
        return [(i['label'], i['units']) for i in self.independents]

    def getDependents(self):
        return [(d['category'], d['label'], d['units']) for d in self.dependents]

    def addParam(self, name, data):
        for p in self.parameters:
            if p['label'] == name:
                raise errors.ParameterInUseError(name)
        d = dict(label=name, data=data)
        self.parameters.append(d)
    
    def getParameter(self, name, case_sensitive=True):
        for p in self.parameters:
            if case_sensitive:
                if p['label'] == name:
                    return p['data']
            else:
                if p['label'].lower() == name.lower():
                    return p['data']
        raise errors.BadParameterError(name)
    
    def getParamNames(self):
        return [ p['label']  for p in self.parameters ]

    def addComment(self, user, comment):
        self.comments.append((datetime.datetime.now(), user, comment))

    def getComments(self, limit, start):
        if limit is None:
            comments = self.comments[start:]
        else:
            comments = self.comments[start:start+limit]
        return comments, start + len(comments)

    def numComments(self):
        return len(self.comments)

class CsvListData(IniData):
    """
    Data backed by a csv-formatted file.

    Stores the entire contents of the file in memory as a list or numpy array
    """

    def __init__(self, filename, file_timeout=FILE_TIMEOUT, data_timeout=DATA_TIMEOUT):
        self.filename = filename
        self._file = SelfClosingFile(open_args=(filename, 'a+'), timeout=file_timeout)
        self.timeout = data_timeout
        self.infofile = filename[:-4] + '.ini'

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
            raise errors.BadDataError(self.cols, len(data[0]))

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

    def __init__(self, filename):
        self.filename = filename
        self._file = SelfClosingFile(open_args=(filename, 'a+'))
        self.infofile = filename[:-4] + '.ini'

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
            raise errors.BadDataError(self.cols, data.shape[-1])

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

def create_backend(filename):
    """Make a data object that manages in-memory and on-disk storage for a dataset.

    filename should be specified without a file extension. If there is an existing
    file in csv format, we create a backend of the appropriate type. If
    no file exists, we create a new backend to store data in binary form.
    """
    csv_file = filename + '.csv'
    if os.path.exists(csv_file):
        if use_numpy:
            return CsvNumpyData(csv_file)
        else:
            return CsvListData(csv_file)
    else:
        if use_numpy:
            return CsvNumpyData(csv_file)
        else:
            return CsvListData(csv_file)
