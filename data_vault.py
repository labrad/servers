#!c:\python25\python.exe

# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

from labrad import types as T, util
from labrad.server import LabradServer, setting

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from ConfigParser import SafeConfigParser
import os
from datetime import datetime

# TODO: make sure this is cross-platform
# TODO: data store configuration should be flexible
DATADIR = 'R:\\_LabRAD Data Server Files_\\'
PRECISION = 6
FILE_TIMEOUT = 60 # how long to keep datafiles open if not accessed
TIME_FORMAT = '%Y-%m-%d, %H:%M:%S'

class NoSessionError(T.Error):
    """Please open a session first."""
    code = 1

class NoDatasetError(T.Error):
    """Please open a dataset first."""
    code = 2

class DatasetNotFoundError(T.Error):
    code = 8
    def __init__(self, name):
        self.msg="Dataset '%s' not found!" % name

class DatasetLockedError(T.Error):
    """Cannot change format of datasets once data has been added."""
    code = 3

class ReadOnlyError(T.Error):
    """Points can only be added to datasets created with 'New Dataset'."""
    code = 4

class NotReadyError(T.Error):
    code = 5
    def __init__(self, name):
        self.msg = "Dataset '%s' is still being initialized." % name

class BadDataError(T.Error):
    code = 6
    def __init__(self, varcount):
        self.msg = 'Dataset requires %d values per datapoint.' % varcount

class BadParameterError(T.Error):
    code = 7
    def __init__(self, name):
        self.msg = "Parameter '%s' not found." % name

class ParameterInUseError(T.Error):
    code = 8
    def __init__(self, name):
        self.msg = "Already a parameter called '%s'." % name

encodings = [
    ('%','%p'),
    ('/','%f'),
    ('\\','%b'),
    (':','%c'),
    ('*','%a'),
    ('?','%q'),
    ('"','%Q'),
    ('<','%l'),
    ('>','%g'),
    ('|','%P')
]

def dsEncode(name):
    for char, code in encodings:
        name = name.replace(char, code)
    return name

def dsDecode(name):
    for char, code in encodings[1:] + encodings[0:1]:
        name = name.replace(code, char)
    return name

def timeToStr(t):
    return t.strftime(TIME_FORMAT)

def timeFromStr(s):
    return datetime.strptime(s, TIME_FORMAT)

class Session:
    def __init__(self, name):
        self.dir = DATADIR + dsEncode(name)
        self.infofile = self.dir + '\\session.ini'
        self.listeners = []
        self.datasets = {}

        if os.access(self.dir, os.R_OK or os.W_OK):
            self.load()
        else:
            os.mkdir(self.dir)
            self.counter = 1
            self.created = self.modified = datetime.now()

        self.access() # update current access time and save

    def load(self):
        S = SafeConfigParser()
        S.read(self.infofile)

        sec = 'File System'
        self.counter = S.getint(sec, 'Counter')

        sec = 'Information'
        self.created = timeFromStr(S.get(sec, 'Created'))
        self.accessed = timeFromStr(S.get(sec, 'Accessed'))
        self.modified = timeFromStr(S.get(sec, 'Modified'))

    def save(self):
        S = SafeConfigParser()

        sec = 'File System'
        S.add_section(sec)
        S.set(sec, 'Counter', repr(self.counter))

        sec = 'Information'
        S.add_section(sec)
        S.set(sec, 'Created',  timeToStr(self.created))
        S.set(sec, 'Accessed', timeToStr(self.accessed))
        S.set(sec, 'Modified', timeToStr(self.modified))

        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        self.accessed = datetime.now()
        self.save()

    def getDSList(self):
        files = os.listdir(self.dir)
        return [(int(f[:5]), dsDecode(f[:-4]))
                for f in files if f.endswith('.csv')]

    def listDatasets(self, startAt=0):
        """Get a list of datasets in this session."""
        if self.counter > startAt:
            datasets = self.getDSList()
            names = [name for num, name in datasets if num >= startAt]
            if len(datasets):
                nextset = max(num for num, name in datasets) + 1
            else:
                nextset = 1
            return sorted(names), nextset
        else:
            return [], startAt or 1

    def waitForDatasets(self, timeout):
        timeout = min(timeout, 300)
        d = defer.Deferred()
        self.listeners.append(d)
        return util.maybeTimeout(d, timeout, None)

    def newDataset(self, title):
        num = self.counter
        self.counter += 1
        self.modified = datetime.now()

        name = '%05d - %s' % (num, title)
        dataset = Dataset(self, name, title, create=True)
        self.datasets[name] = dataset
        self.notifyListeners()
        self.access()
        return dataset

    def openDataset(self, name):
        # first lookup by number if necessary
        if isinstance(name, (int, long)):
            for num, oldName in self.getDSList():
                if name == num:
                    name = oldName
                    break
        # if it's still a number, we didn't find the set
        if isinstance(name, (int, long)):
            raise DatasetNotFoundError(name)

        filename = dsEncode(name)
        if not os.access('%s\\%s.csv' % (self.dir, filename), os.R_OK):
            raise DatasetNotFoundError(name)

        if name in self.datasets:
            if not self.datasets[name].locked:
                raise NotReadyError(name)
            dataset = self.datasets[name]
            dataset.access()
        else:
            # need to create a new wrapper for this dataset
            dataset = Dataset(self, name)
            self.datasets[name] = dataset
        self.access()
        return dataset

    def notifyListeners(self):
        for d in self.listeners:
            reactor.callLater(0, d.callback, None)
        self.listeners = []

class Dataset:
    def __init__(self, session, name, title=None, num=None, create=False):
        self.name = name
        file_base = '%s\\%s' % (session.dir, dsEncode(name))
        self.datafile = file_base + '.csv'
        self.infofile = file_base + '.ini'
        self.file # create the datafile, but don't do anything with it
        self.listeners = []

        if create:
            self.locked = False
            self.title = title
            
            self.created = self.accessed = self.modified = datetime.now()

            self.independent = []
            self.dependent = []
            self.parameters = []
            self.save()
        else:
            self.locked = True
            self.load()
            self.access()

    def load(self):
        S = SafeConfigParser()
        S.read(self.infofile)

        gen = 'General'
        self.title = S.get(gen, 'Title', raw=True)
        self.created = timeFromStr(S.get(gen, 'Created'))
        self.accessed = timeFromStr(S.get(gen, 'Accessed'))
        self.modified = timeFromStr(S.get(gen, 'Modified'))

        def getInd(i):
            sec = 'Independent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            return dict(label=label, units=units)
        count = S.getint(gen, 'Independent')
        self.independent = [getInd(i) for i in range(count)]

        def getDep(i):
            sec = 'Dependent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            categ = S.get(sec, 'Category', raw=True)
            return dict(label=label, units=units, category=categ)
        count = S.getint(gen, 'Dependent')
        self.dependent = [getDep(i) for i in range(count)]

        def getPar(i):
            sec = 'Parameter %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            # TODO: big security hole! evaluate in restricted namespace
            data = T.evalLRData(S.get(sec, 'Data', raw=True))
            return dict(label=label, data=data)
        count = S.getint(gen, 'Parameters')
        self.parameters = [getPar(i) for i in range(count)]

    def save(self):
        S = SafeConfigParser()
        
        sec = 'General'
        S.add_section(sec)
        S.set(sec, 'Created',  timeToStr(self.created))
        S.set(sec, 'Accessed', timeToStr(self.accessed))
        S.set(sec, 'Modified', timeToStr(self.modified))
        S.set(sec, 'Title',       self.title)
        S.set(sec, 'Independent', repr(len(self.independent)))
        S.set(sec, 'Dependent',   repr(len(self.dependent)))
        S.set(sec, 'Parameters',  repr(len(self.parameters)))

        for i, ind in enumerate(self.independent):
            sec = 'Independent %d' % (i+1)
            S.add_section(sec)
            S.set(sec, 'Label', ind['label'])
            S.set(sec, 'Units', ind['units'])

        for i, dep in enumerate(self.dependent):
            sec = 'Dependent %d' % (i+1)
            S.add_section(sec)
            S.set(sec, 'Label',    dep['label'])
            S.set(sec, 'Units',    dep['units'])
            S.set(sec, 'Category', dep['category'])

        for i, par in enumerate(self.parameters):
            sec = 'Parameter %d' % (i+1)
            S.add_section(sec)
            S.set(sec, 'Label', par['label'])
            # TODO: smarter saving here, since eval'ing is a big security hole
            S.set(sec, 'Data', repr(par['data']))

        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        self.accessed = datetime.now()
        self.save()

    @property
    def file(self):
        """Open the datafile on demand.

        The file is also scheduled to be closed
        if it has not accessed for a while.
        """
        if not hasattr(self, '_file'):
            #print 'opening:', self.datafile
            self._file = open(self.datafile, 'a+') # append data
            self._fileTimeoutCall = reactor.callLater(
                                      FILE_TIMEOUT, self._fileTimeout)
        else:
            #print 'extending timeout:', self.datafile
            self._fileTimeoutCall.reset(FILE_TIMEOUT)
        return self._file

    def _fileTimeout(self):
        #print 'closing:', self.datafile
        self._file.close()
        del self._file
        del self._fileTimeoutCall

    def addIndependent(self, label, units):
        if self.locked:
            raise DatasetLockedError()

        d = dict(label=label, units=units)
        self.independent.append(d)
        self.save()

        if units:
            label += ' [%s]' % units
        return label

    def addDependent(self, label, legend, units):
        if self.locked:
            raise DatasetLockedError()

        d = dict(category=label, label=legend, units=units)
        self.dependent.append(d)
        self.save()

        if legend:
            label += ' (%s)' % legend
        if units:
            label += ' [%s]' % units
        return label

    def addParameter(self, name, data):
        for p in self.parameters:
            if p['label'] == name:
                raise ParameterInUseError(name)
        d = dict(label=name, data=data)
        self.parameters.append(d)
        self.save()
        return name

    def waitForData(self, timeout):
        timeout = min(timeout, 300)
        d = defer.Deferred()
        self.listeners.append(d)
        return util.maybeTimeout(d, timeout, None)

    def notifyListeners(self):
        for defs in self.listeners:
            reactor.callLater(0, defs.callback, None)
        self.listeners = []

    def getParameter(self, name):
        for p in self.parameters:
            if p['label'] == name:
                return p['data']
        raise BadParameterError(name)


class DataVault(LabradServer):
    name = 'Data Vault'

    sessions = {}

    @setting(10, 'List Sessions', returns=['*s: Available sessions'])
    def list_sessions(self, c):
        """Get a list of all registered sessions."""
        return sorted(dsDecode(s) for s in os.listdir(DATADIR))

    @setting(11, 'New Session', name=['s'], returns=['s'])
    def new_session(self, c, name='_unnamed_'):
        """Create a new session.

        If the specified session exists, an error is raised.
        The returned string is the path to the session folder.
        """
        if name in self.list_sessions(c):
            raise T.Error("Session '%s' already exists." % name)
        else:
            session = self.sessions[name] = Session(name)
        self.updateSessionContext(c, name)
        return session.dir

    @setting(12, 'Open Session', name=['s'], create=['b'], returns=['s'])
    def open_session(self, c, name='_unnamed_', create=False):
        """Open a session.

        If the optional create flag is True (default: False), a
        new session will be created if it does not yet exist.
        The returned string is the path to the session folder.
        """
        if name in self.list_sessions(c):
            if name not in self.sessions: # hasn't been loaded yet
                self.sessions[name] = Session(name)
            session = self.sessions[name]
            session.access() # update time of last access
        else:
            if not create:
                raise T.Error("Cannot create new session. Use 'New Session'.")
            session = self.sessions[name] = Session(name)
        self.updateSessionContext(c, name)
        return session.dir

    def updateSessionContext(self, c, name):
        if 'dataset' in c:
            del c['dataset']
        c['session'] = name
        c['nextset'] = 1 # start from the beginning of the datasets

    def getSession(self, c):
        try:
            name = c['session']
            return self.sessions[name]
        except KeyError:
            raise NoSessionError()

    def getDataset(self, c):
        try:
            session = self.getSession(c)
            name = c['dataset']
            return session.datasets[name]
        except KeyError:
            raise NoDatasetError()

    @setting(20, 'List Datasets', returns=['*s'])
    def list_datasets(self, c):
        """Get a list of all datasets in the current session.

        You must first call "Open Session" to specify the session
        for which to retrieve datasets.
        """
        session = self.getSession(c)
        datasets, c['nextset'] = session.listDatasets()
        return datasets

    @setting(21, 'List New Datasets', timeout=['v[s]'], returns=['*s'])
    def list_new_datasets(self, c, timeout=None):
        """Get a list of new datasets in the current session.

        You must first call "Open Session" to specify the session
        for which to retrieve datasets.
        """
        session = self.getSession(c)
        ns = c['nextset']
        datasets, ns = session.listDatasets(startAt=ns)
        if timeout and not len(datasets):
            yield session.waitForDatasets(timeout)
            datasets, ns = session.listDatasets(startAt=ns)
        c['nextset'] = ns
        returnValue(datasets)

    @setting(22, 'New Dataset', name=['s'], returns=['s'])
    def new_dataset(self, c, name='untitled'):
        """Create a new Dataset.

        Returns a string with the path to the .csv data file.
        """
        session = self.getSession(c)
        dataset = session.newDataset(name)
        c['dataset'] = dataset.name # not the same as name: has number prefixed
        c['filepos'] = 0 # start at the beginning
        c['writing'] = True
        return dataset.datafile

    @setting(23, 'Open Dataset', name=['s', 'w'], returns=['s'])
    def open_dataset(self, c, name):
        """Open a Dataset for reading."""
        session = self.getSession(c)
        dataset = session.openDataset(name)
        c['dataset'] = name
        c['filepos'] = 0
        c['writing'] = False
        return dataset.datafile

    @setting(100, 'List Independents', returns=['*2s'])
    def list_independents(self, c):
        """Get a list of independent variables."""
        return self.getVariables(c, 'independent', ['label', 'units'])

    @setting(101, 'Add Independent',
             label=['s'], units=['s'], returns=['s'])
    def add_independent(self, c, label='untitled', units=''):
        """Add an independent variable."""
        dataset = self.getDataset(c)
        return dataset.addIndependent(label, units)

    @setting(110, 'List Dependents', returns=['*2s'])
    def list_dependents(self, c):
        """Get a list of dependent variables."""
        return self.getVariables(c, 'dependent', ['category', 'label', 'units'])

    @setting(111, 'Add Dependent',
             label=['s'], legend=['s'], units=['s'], returns=['s'])
    def add_dependent(self, c, label='untitled', legend='', units=''):
        """Add a dependent variable."""
        dataset = self.getDataset(c)
        return dataset.addDependent(label, legend, units)

    def getVariables(self, c, varType, items):
        dataset = self.getDataset(c)
        if not dataset.locked:
            raise NotReadyError(dataset.name)
        vars = getattr(dataset, varType)
        return [[var[item] for item in items] for var in vars]

    @setting(120, 'List Parameters', returns=['*s'])
    def list_parameters(self, c):
        """Get a list of parameters."""
        dataset = self.getDataset(c)
        return [par['label'] for par in dataset.parameters]

    @setting(121, 'Add Parameter', name=['s'], returns=[''])
    def add_parameter(self, c, name, data):
        """Add a new parameter to the current dataset."""
        dataset = self.getDataset(c)
        dataset.addParameter(name, data)

    @setting(122, 'Get Parameter', name=['s'])
    def get_parameter(self, c, name):
        """Get a parameter value."""
        dataset = self.getDataset(c)
        return dataset.getParameter(name)

    @setting(200, 'Add Data',
                  data=['*v: add one row of data',
                        '*2v: add multiple rows of data'])
    def add_data(self, c, data):
        """Add data to the current dataset."""
        dataset = self.getDataset(c)

        if not c['writing']:
            raise ReadOnlyError()

        varcount = len(dataset.independent) + len(dataset.dependent)
        if not len(data) or not isinstance(data[0], list):
            data = [data]
        if len(data[0]) != varcount:
            raise BadDataError(varcount)

        f = dataset.file
        f.seek(c['filepos'])
        for row in data:
            f.write(', '.join('%.*G' % (PRECISION, v) for v in row) + '\n')
        f.flush()
        c['filepos'] = f.tell()
        
        dataset.locked = True
        dataset.notifyListeners()

    @setting(250, 'Get Data', returns=['*2v'])
    def get_data(self, c):
        """Get all data in the current dataset."""
        dataset = self.getDataset(c)
        return self.readRest(dataset, c, startOver=True)

    @setting(251, 'Get New Data', timeout=['v[s]'], returns=['*2v'])
    def get_new_data(self, c, timeout=None):
        """Get new data from dataset in this context."""
        dataset = self.getDataset(c)
        V = self.readRest(dataset, c)
        if timeout and not len(V):
            yield dataset.waitForData(timeout)
            V = self.readRest(dataset, c)
        returnValue(V)

    def readRest(self, dataset, c, startOver=False):
        """Read the rest of the values from a datafile."""
        if not dataset.locked:
            raise NotReadyError(dataset.name)
        f = dataset.file
        pos = 0 if startOver else c['filepos']
        f.seek(pos)
        lines = f.readlines()
        c['filepos'] = f.tell()
        return [[float(n) for n in line.split(',')] for line in lines]


__server__ = DataVault()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
