#!c:\python25\python.exe

from __future__ import with_statement

from labrad import types as T, util
from labrad.server import LabradServer, setting
from labrad.errors import Error
from twisted.internet import defer, reactor
from ConfigParser import SafeConfigParser
import os
import time
import re

DSDATADIR = 'R:\\_DMS Data Server Files_\\'
DS_PRECISION = 6

FILE_TIMEOUT = 60 # how long to keep datafiles open if not accessed

class NoSessionError(Error):
    """Please open a session first."""
    code = 1

class NoDatasetError(Error):
    """Please open a dataset first."""
    code = 2

class DatasetLockedError(Error):
    """Cannot change format of datasets once data has been added!"""
    code = 3

class ReadOnlyError(Error):
    """Points can only be added to datasets created with 'New Dataset'"""
    code = 4

class NotReadyError(Error):
    code = 5
    def __init__(self, name):
        self.msg = "Dataset '%s' is still being initialized! Please try again later." % name

class BadDataError(Error):
    code = 6
    def __init__(self, varcount):
        self.msg = "This plot requires %d values per datapoint!" % varcount

class BadParameterError(Error):
    code = 7
    def __init__(self, name):
        self.msg = "Parameter '%s' not found in dataset!" % name

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

def rematch(re, string):
    result = re.findall(string)
    if len(result) == 0:
        result = ""
    else:
        result = result[0].strip()
    return result

TIME_FORMAT = '%Y-%m-%d, %H:%M:%S'

def timeToStr(t):
    return time.strftime(TIME_FORMAT, t)

def timeFromStr(t):
    return time.strptime(t, TIME_FORMAT)

class Session:
    def __init__(self, name):
        t = time.localtime()
        self.dir = DSDATADIR + dsEncode(name)
        self.infofile = self.dir + '\\session.ini'
        self.listeners = []
        self.datasets = {}

        if os.access(self.dir, os.R_OK or os.W_OK):
            self.load()
        else:
            os.mkdir(self.dir)
            self.counter = 1
            self.created = t
            self.modified = t

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
        self.accessed = time.localtime()
        self.save()

    def listDatasets(self, startAt=0):
        if self.counter > startAt:
            datasets_raw = os.listdir(self.dir)
            datasets = [(int(f[0:5]), dsDecode(f[0:-4])) for f in datasets_raw
                                                         if f.endswith('.csv')]
            names = [name for num, name in datasets if num >= startAt]
            names.sort()
            if len(datasets):
                nextset = max((num for num, name in datasets)) + 1
            else:
                nextset = 1
            return names, nextset
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
        self.modified = time.localtime()

        name = '%05d - %s' % (num, title)
        dataset = Dataset(self, name, title, create=True)
        self.datasets[name] = dataset
        self.notifyListeners()
        self.access()
        return dataset

    def openDataset(self, name):
        filename = dsEncode(name)
        if not os.access('%s\\%s.csv' % (self.dir, filename), os.R_OK):
            raise DMSError(code=8, msg="Dataset '%s' not found!" % name)

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
        for defs in self.listeners:
            reactor.callLater(0, defs.callback, None)
        self.listeners = []

class Dataset:
    def __init__(self, session, name, title=None, num=None, create=False):
        t = time.localtime()

        self.name = name
        file_base = '%s\\%s' % (session.dir, dsEncode(name))
        self.datafile = file_base + '.csv'
        self.infofile = file_base + '.ini'
        self.file # create the datafile, but don't do anything with it
        self.listeners = []

        if create:
            self.locked = False
            self.title = title
            
            self.created = t
            self.accessed = t
            self.modified = t

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

        sec = 'General'
        self.created = timeFromStr(S.get(sec, 'Created'))
        self.accessed = timeFromStr(S.get(sec, 'Accessed'))
        self.modified = timeFromStr(S.get(sec, 'Modified'))
        self.title = S.get(sec, 'Title', raw=True)

        def getInd(i):
            sec = 'Independent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            return dict(label=label, units=units)
        count = S.getint('General', 'Independent')
        self.independent = [getInd(i) for i in range(count)]

        def getDep(i):
            sec = 'Dependent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            categ = S.get(sec, 'Category', raw=True)
            return dict(label=label, units=units, category=categ)
        count = S.getint('General', 'Dependent')
        self.dependent = [getDep(i) for i in range(count)]

        def getPar(i):
            sec = 'Parameter %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            ptype = S.get(sec, 'Type', raw=True)
            par = dict(label=label, type=ptype)
            if ptype == 'Value':
                par.update(
                    value = float(S.get(sec, 'Value', raw=True)),
                    units =       S.get(sec, 'Units', raw=True)
                )
            return par
        count = S.getint('General', 'Parameters')
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
            S.set(sec, 'Type',  par['type'])
            if par['type'] == 'Value':
                S.set(sec, 'Value', repr(par['value']))
                S.set(sec, 'Units',      par['units'])

        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        self.accessed = time.localtime()
        self.save()

    @property
    def file(self):
        """open the datafile on demand, and schedule it to be closed
        if it's not accessed for a while."""
        if not hasattr(self, '_file'):
            print 'opening:', self.datafile
            self._file = open(self.datafile, 'a+') # append data
            self._fileTimeoutCall = reactor.callLater(
                                      FILE_TIMEOUT, self._fileTimeout)
        else:
            #print 'extending timeout:', self.datafile
            self._fileTimeoutCall.reset(FILE_TIMEOUT)
        return self._file

    def _fileTimeout(self):
        print 'closing:', self.datafile
        self._file.close()
        del self._file
        del self._fileTimeoutCall

    def addIndependent(self, label, units):
        if self.locked:
            raise DatasetLockedError()

        self.independent.append(dict(label=label, units=units))
        self.save()

        s = label
        if units:
            s += ' [%s]' % units
        return s

    def addDependent(self, label, legend, units):
        if self.locked:
            raise DatasetLockedError()

        self.dependent.append(dict(category=label, label=legend, units=units))
        self.save()

        s = label
        if legend:
            s += ' (%s)' % legend
        if units:
            s += ' [%s]' % units
        return s

    def addParameter(self, name):
        self.parameters.append(dict(label=name, type='Notifier'))
        self.save()
        return name

    def updateLastParameter(self, data):
        par = self.parameters[-1]
        par.update(
            type = 'Value',
            value = data.value,
            units = data.units
        )
        self.save()

    def notifyListeners(self):
        for defs in self.listeners:
            reactor.callLater(0, defs.callback, None)
        self.listeners = []

    def getParameter(self, name):
        P = None
        for par in self.parameters:
            if par['label'] == name:
                P = par
                break

        if P is None:
            raise BadParameterError(name)

        if P['type'] == 'Value':
            return T.Value(P['value'], P['units'])

        if P['type'] == 'Notifier':
            return None

class DataServer(LabradServer):
    name = 'Data Server'

    sessions = {}

    re_label  = re.compile('^([^\[\(]*)')
    re_units  = re.compile('\[([^\]]*)')
    re_legend = re.compile('\(([^\)]*)')
    re_data   = re.compile(',?[ ]*([\-0-9\.][\-0-9Ee\.]*)')

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

    @setting(1, 'List Sessions',
                data=[': Retrieve session list'],
                returns=['*s: Available sessions'])
    def list_sessions(self, c, data):
        """Retrieves a list of all registered sessions."""
        sessions_raw = os.listdir(DSDATADIR)
        sessions = [dsDecode(session) for session in sessions_raw]
        sessions.sort()
        return sessions

    @setting(10, 'Open Session',
                 name=[': Uses "_unnamed_" as the session title',
                       's: Session title'],
                 returns=['s: Path to session folder'])
    def open_session(self, c, name='_unnamed_'):
        """Opens a session
        NOTE:
        If the specified session does not exist, it is created.
        """
        if 'dataset' in c:
            del c['dataset']
            
        if name in self.sessions:
            session = self.sessions[name]
            session.access() # update time of last access
        else:
            session = self.sessions[name] = Session(name)

        c['session'] = name
        c['nextset'] = 1 # start from the beginning of the datasets
        return session.dir

    @setting(20, 'List Datasets',
                 data=[': Retrieve dataset list'],
                 returns=['*s: Available datasets'])
    def list_datasets(self, c, data):
        """Retrieves a list of all datasets in the current session
        NOTE:
        "Open Session" must first be used to specify the session
        for which to retrieve the datasets.
        """
        session = self.getSession(c)
        datasets, c['nextset'] = session.listDatasets()
        return datasets

    @setting(21, 'List New Datasets',
                 data=[': Return immediately if no new datasets found',
                       'v[s]: Wait specified time for new datasets'],
                 returns=['*s: New datasets'])
    def list_new_datasets(self, c, data):
        """Retrieves a list of new datasets in the current session
        NOTE:
        "Open Session" must first be used to specify the session
        for which to retrieve the datasets.
        """
        session = self.getSession(c)

        ns = c['nextset']
        datasets, ns = session.listDatasets(startAt=ns)
        if (len(datasets) == 0) and isinstance(data, T.Value):
            yield session.waitForDatasets(data.value)
            datasets, ns = session.listDatasets(startAt=ns)

        c['nextset'] = ns
        returnValue(datasets)

    @setting(100, 'New Dataset',
                  name=[': Create dataset named "untitled"',
                        's: Create dataset under given name'],
                  returns=['s: Path to *.csv file containing data'])
    def new_dataset(self, c, name='untitled'):
        """Creates a new Dataset"""
        session = self.getSession(c)
        dataset = session.newDataset(name)

        c['dataset'] = dataset.name # not the same as name: has number prefixed
        c['filepos'] = 0
        c['writing'] = True
        
        return dataset.datafile

    @setting(110, 'Add Independent Variable',
                  data=['', 's', '*s'],
                  returns=['s'])
    def add_independent(self, c, data):
        """Adds an independent variable"""
        dataset = self.getDataset(c)
        
        if data is None:
            label, units = 'untitled', ''
        if isinstance(data, str):
            label = rematch(self.re_label, data)
            units = rematch(self.re_units, data)
        if isinstance(data, list):
            if len(data)==0:
                data = ['untitled']
            data.append('')
            label, units = data[:2]

        return dataset.addIndependent(label, units)

    @setting(120, 'Add Dependent Variable',
                  data=['', 's', '*s'],
                  returns=['s'])
    def add_dependent(self, c, data):
        """Creates a new dataset"""
        dataset = self.getDataset(c)

        if data is None:
            label, legend, units = 'untitled', '', ''
        if isinstance(data, str):
            label = rematch(self.re_label, data)
            legend = rematch(self.re_legend, data)
            units = rematch(self.re_units, data)
        if isinstance(data, list):
            if len(data)==0:
                data = ['untitled']
            data.extend(['', ''])
            label, legend, units = data[:3]
                
        return dataset.addDependent(label, legend, units)

    @setting(130, 'Add Parameter', data=['', 's'], returns=['s'])
    def add_parameter(self, c, data='untitled'):
        """Creates a new dataset"""
        dataset = self.getDataset(c)
        dataset.addParameter(data)
        return data

    @setting(131, 'Set Parameter', data=['v'])
    def set_parameter(self, c, data):
        """Sets a parameter value"""
        dataset = self.getDataset(c)
        dataset.updateLastParameter(data)
        return data

    @setting(150, 'Add Datapoint', data=['*v'])
    def add_datapoint(self, c, data):
        """Adds data to the given dataset."""
        dataset = self.getDataset(c)

        if not c['writing']:
            raise ReadOnlyError()

        varcount = len(dataset.independent) + len(dataset.dependent)
        if len(data.values) % varcount:
            raise BadDataError(varcount)

        dat = [data.values[i:i+varcount]
               for i in range(0, len(data.values), varcount)]

        f = dataset.file
        f.seek(c['filepos'])
        for line in dat:
            f.write(', '.join('%.*G' % (DS_PRECISION, d) for d in line)+'\n')
        f.flush()
        c['filepos'] = f.tell()
        
        dataset.locked = True
        dataset.notifyListeners()

    @setting(200, 'Open Dataset', name=['', 's'], returns=['s'])
    def open_dataset(self, c, name='untitled'):
        """Opens a Dataset for reading"""
        session = self.getSession(c)
        dataset = session.openDataset(name)

        c['dataset'] = name
        c['filepos'] = 0
        c['writing'] = False
        
        return dataset.datafile

    def getVariables(self, c, varType, items):
        dataset = self.getDataset(c)
        
        if not dataset.locked:
            raise NotReadyError(dataset.name)

        vars = getattr(dataset, varType)
        s = [var[item] for item in items for var in vars]
        return s

    @setting(210, 'Get Independent Variables', data=[''], returns=['*s'])
    def get_independents(self, c, data):
        """Get independent variables"""
        return self.getVariables(c, 'independent', ['label', 'units'])
        
    @setting(220, 'Get Dependent Variables', data=[''], returns=['*s'])
    def get_dependents(self, c, data):
        """Get dependent variables"""
        return self.getVariables(c, 'dependent', ['category', 'label', 'units'])

    @setting(230, 'List Parameters', data=[''], returns=['*s'])
    def list_parameters(self, c, data):
        """List parameters"""
        dataset = self.getDataset(c)
        s = [par['label'] for par in dataset.parameters]
        return s

    @setting(231, 'Get Parameter', data=['s'])
    def get_parameter(self, c, data):
        """Get a parameter"""
        dataset = self.getDataset(c)
        return dataset.getParameter(data)

    @setting(250, 'Get All Datapoints', data=[''], returns=['*v'])
    def get_all_datapoints(self, c, data):
        """Get all datapoints"""
        dataset = self.getDataset(c)

        if not dataset.locked:
            raise NotReadyError(data)

        V = self.readRest(dataset, c, startOver=True)
        return V

    @setting(251, 'Get New Datapoints', data=['', 'v[s]'], returns=['*v'])
    def get_new_datapoints(self, c, data):
        """Get new datapoints"""
        dataset = self.getDataset(c)

        if not dataset.locked:
            raise NotReadyError(name)

        V = self.readRest(dataset, c)

        if len(V) == 0 and isinstance(data, T.Value):
            dreturn, (dtimeout, ddata) = util.firstToFire()
            reactor.callLater(min(data.value, 300), dtimeout.callback, None)
            dataset.listeners.append(ddata)
            yield dreturn

            V = self.readRest(dataset, c)

        returnValue(V)

    def readRest(self, dataset, c, startOver=False):
        """Read the rest of the values from a datafile."""
        f = dataset.file
        if startOver:
            f.seek(0)
        else:
            f.seek(c['filepos'])
        lines = f.readlines()
        c['filepos'] = f.tell()
        V = [float(entry) for line in lines
                          for entry in self.re_data.findall(line)]
        return V
    

__server__ = DataServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    
