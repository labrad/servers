#!/usr/bin/python
# Copyright (C) 2012  Matthew Neeley
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
"""
### BEGIN NODE INFO
[info]
name = Data Vault Multihead
version = 2.3.5-hydra
description = Store and retrieve numeric data

[startup]
cmdline = %PYTHON% %FILE% --auto
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from __future__ import with_statement

import labrad
from labrad import constants, types as T, util
from labrad.server import LabradServer, Signal, setting

from twisted.application.service import MultiService
from twisted.application.internet import TCPClient
from twisted.internet import reactor
from twisted.internet.reactor import callLater
from twisted.internet.defer import inlineCallbacks

from ConfigParser import SafeConfigParser

import os
import warnings
import time

def lock_path(d):
    '''
    Lock a directory and return a file descriptor corresponding to the lockfile
    
    This lock is non-blocking and throws an exception if it can't get the lock.
    The user is expected to fix this.
    '''
    if os.name != "posix":
        warnings.warn('File locks only available on POSIX.  Be very careful not to run two copies of the data vault')
        return
    import fcntl
    filename = os.path.join(d, 'lockfile')
    fd = os.open(filename, os.O_CREAT|os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
    except IOError:
        raise RuntimeError('Unable to acquire filesystem lock.  Data vault already running!')
    if os.fstat(fd).st_size < 1:
        os.write(fd, "If you delete this file without understanding it will cause you great pain\n")
    return fd

def unlock(fd):
    '''
    We don't actually use this, since we hold the lock until the datavault exits
    and let the OS clean up.
    '''
    if os.name != "posix":
        warnings.warn('File locks only available on POSIX.  Be very careful not to run two copies of the data vault')
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_UN)
    
# ConfigParser is retarded and doesn't let you choose your newline separator,
# so we overload it to make data vault files consistent across OSes.
# In particular, Windows expects \r\n whereas Linux uses \n
class ExtendedContext(object):
    '''
    This is an extended context that contains the manager.  This prevents multiple
    contexts with the same client ID from conflicting if they are connected
    to different managers.
    '''
    def __init__(self, server, ctx):
        self.__server = server
        self.__ctx = ctx
    @property
    def server(self):
        return self.__server
    @property
    def context(self):
        return self.__ctx

    def __eq__(self, other):
        return (self.context == other.context) and (self.server == other.server)
    def __ne__(self, other):
        return not (self == other)
    def __hash__(self):
        return hash(self.context) ^ hash(self.server.host) ^ self.server.port

class DVSafeConfigParser(SafeConfigParser):
    def write(self, fp, newline='\r\n'):
        """Write an .ini-format representation of the configuration state."""
        if self._defaults:
            fp.write("[%s]" % DEFAULTSECT + newline)
            for (key, value) in self._defaults.items():
                fp.write(("%s = %s" + newline) % (key, str(value).replace('\n', '\n\t')))
            fp.write(newline)
        for section in self._sections:
            fp.write("[%s]" % section + newline)
            for (key, value) in self._sections[section].items():
                if key != "__name__":
                    fp.write(("%s = %s" + newline) %
                             (key, str(value).replace('\n', '\n\t')))
            fp.write(newline)

import os, re
import time
from datetime import datetime
import weakref

try:
    import numpy as np
    print "Numpy imported."
    useNumpy = True
except ImportError, e:
    print e
    print "Numpy not imported.  The DataVault will operate, but will be slower."
    useNumpy = False


# TODO: tagging
# - search globally (or in some subtree of sessions) for matching tags
#     - this is the least common case, and will be an expensive operation
#     - don't worry too much about optimizing this
#     - since we won't bother optimizing the global search case, we can store
#       tag information in the session


# location of repository will get loaded from the registry
DATADIR = None

PRECISION = 12 # digits of precision to use when saving data
DATA_FORMAT = '%%.%dG' % PRECISION
FILE_TIMEOUT = 60 # how long to keep datafiles open if not accessed
DATA_TIMEOUT = 300 # how long to keep data in memory if not accessed
TIME_FORMAT = '%Y-%m-%d, %H:%M:%S'


## error messages

class NoDatasetError(T.Error):
    """Please open a dataset first."""
    code = 2

class DatasetNotFoundError(T.Error):
    code = 3
    def __init__(self, name):
        self.msg="Dataset '%s' not found!" % name

class DirectoryExistsError(T.Error):
    code = 4
    def __init__(self, name):
        self.msg = "Directory '%s' already exists!" % name

class DirectoryNotFoundError(T.Error):
    code = 5

class EmptyNameError(T.Error):
    """Names of directories or keys cannot be empty"""
    code = 6
    def __init__(self, path):
        self.msg = "Directory %s does not exist!" % (path,)
        
class ReadOnlyError(T.Error):
    """Points can only be added to datasets created with 'new'."""
    code = 7

class BadDataError(T.Error):
    code = 8
    def __init__(self, varcount, gotcount):
        self.msg = 'Dataset requires %d values per datapoint not %d.' % (varcount, gotcount)

class BadParameterError(T.Error):
    code = 9
    def __init__(self, name):
        self.msg = "Parameter '%s' not found." % name

class ParameterInUseError(T.Error):
    code = 10
    def __init__(self, name):
        self.msg = "Already a parameter called '%s'." % name


## filename translation
        
encodings = [
    ('%','%p'),
    ('/','%f'),
    ('\\','%b'),
    (':','%c'),
    ('*','%a'),
    ('?','%q'),
    ('"','%r'),
    ('<','%l'),
    ('>','%g'),
    ('|','%v')
]

def dsEncode(name):
    for char, code in encodings:
        name = name.replace(char, code)
    return name

def dsDecode(name):
    for char, code in encodings[1:] + encodings[0:1]:
        name = name.replace(code, char)
    return name

def filedir(path):
    return os.path.join(DATADIR, *[dsEncode(d) + '.dir' for d in path[1:]])
    
    
## time formatting
    
def timeToStr(t):
    return t.strftime(TIME_FORMAT)

def timeFromStr(s):
    return datetime.strptime(s, TIME_FORMAT)


## variable parsing
    
re_label = re.compile(r'^([^\[(]*)') # matches up to the first [ or (
re_legend = re.compile(r'\((.*)\)') # matches anything inside ( )
re_units = re.compile(r'\[(.*)\]') # matches anything inside [ ]

def getMatch(pat, s, default=None):
    matches = re.findall(pat, s)
    if len(matches) == 0:
        if default is None:
            raise Exception("Cannot parse '%s'." % s)
        return default
    return matches[0].strip()

def parseIndependent(s):
    label = getMatch(re_label, s)
    units = getMatch(re_units, s, '')
    return label, units
    
def parseDependent(s):
    label = getMatch(re_label, s)
    legend = getMatch(re_legend, s, '')
    units = getMatch(re_units, s, '')
    return label, legend, units
    


class Session(object):
    """Stores information about a directory on disk.
    
    One session object is created for each data directory accessed.
    The session object manages reading from and writing to the config
    file, and manages the datasets in this directory.
    """
    
    # keep a dictionary of all created session objects
    _sessions = weakref.WeakValueDictionary()

    @classmethod
    def getAll(cls):
        return cls._sessions.values()
    
    @staticmethod
    def exists(path):
        """Check whether a session exists on disk for a given path.
        
        This does not tell us whether a session object has been
        created for that path.
        """
        return os.path.exists(filedir(path))
    
    def __new__(cls, path, hub):
        """Get a Session object.
        
        If a session already exists for the given path, return it.
        Otherwise, create a new session instance.
        """
        path = tuple(path)
        if path in cls._sessions:
            return cls._sessions[path]
        inst = super(Session, cls).__new__(cls)
        inst._init(path, hub)
        cls._sessions[path] = inst
        return inst

    def _init(self, path, hub):
        """Initialization that happens once when session object is created."""
        self.path = path
        self.hub = hub
        self.dir = filedir(path)
        self.infofile = os.path.join(self.dir, 'session.ini')
        self.datasets = weakref.WeakValueDictionary()

        if not os.path.exists(self.dir):
            os.makedirs(self.dir)
            
            # notify listeners about this new directory
            parentSession = Session(path[:-1], hub)
            hub.onNewDir(path[-1], parentSession.listeners)
           
        if os.path.exists(self.infofile):
            self.load()
        else:
            self.counter = 1
            self.created = self.modified = datetime.now()
            self.session_tags = {}
            self.dataset_tags = {}

        self.access() # update current access time and save
        self.listeners = set()
            
    def load(self):
        """Load info from the session.ini file."""
        S = DVSafeConfigParser()
        S.read(self.infofile)

        sec = 'File System'
        self.counter = S.getint(sec, 'Counter')

        sec = 'Information'
        self.created = timeFromStr(S.get(sec, 'Created'))
        self.accessed = timeFromStr(S.get(sec, 'Accessed'))
        self.modified = timeFromStr(S.get(sec, 'Modified'))

        # get tags if they're there
        if S.has_section('Tags'):
            self.session_tags = eval(S.get('Tags', 'sessions', raw=True))
            self.dataset_tags = eval(S.get('Tags', 'datasets', raw=True))
        else:
            self.session_tags = {}
            self.dataset_tags = {}

    def save(self):
        """Save info to the session.ini file."""
        S = DVSafeConfigParser()

        sec = 'File System'
        S.add_section(sec)
        S.set(sec, 'Counter', repr(self.counter))

        sec = 'Information'
        S.add_section(sec)
        S.set(sec, 'Created',  timeToStr(self.created))
        S.set(sec, 'Accessed', timeToStr(self.accessed))
        S.set(sec, 'Modified', timeToStr(self.modified))

        sec = 'Tags'
        S.add_section(sec)
        S.set(sec, 'sessions', repr(self.session_tags))
        S.set(sec, 'datasets', repr(self.dataset_tags))

        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        """Update last access time and save."""
        self.accessed = datetime.now()
        self.save()

    def listContents(self, tagFilters):
        """Get a list of directory names in this directory."""
        files = os.listdir(self.dir)
        files.sort()
        dirs = [dsDecode(s[:-4]) for s in files if s.endswith('.dir')]
        datasets = [dsDecode(s[:-4]) for s in files if s.endswith('.csv')]
        # apply tag filters
        def include(entries, tag, tags):
            """Include only entries that have the specified tag."""
            return [e for e in entries
                    if e in tags and tag in tags[e]]
        def exclude(entries, tag, tags):
            """Exclude all entries that have the specified tag."""
            return [e for e in entries
                    if e not in tags or tag not in tags[e]]
        for tag in tagFilters:
            if tag[:1] == '-':
                filter = exclude
                tag = tag[1:]
            else:
                filter = include
            #print filter.__name__ + ':', tag
            #print 'before:', dirs, datasets
            dirs = filter(dirs, tag, self.session_tags)
            datasets = filter(datasets, tag, self.dataset_tags)
            #print 'after:', dirs, datasets
        return dirs, datasets
            
    def listDatasets(self):
        """Get a list of dataset names in this directory."""
        files = os.listdir(self.dir)
        files.sort()
        return [dsDecode(s[:-4]) for s in files if s.endswith('.csv')]
    
    def newDataset(self, title, independents, dependents):
        num = self.counter
        self.counter += 1
        self.modified = datetime.now()

        name = '%05d - %s' % (num, title)
        dataset = Dataset(self, name, title, create=True)
        for i in independents:
            dataset.addIndependent(i)
        for d in dependents:
            dataset.addDependent(d)
        self.datasets[name] = dataset
        self.access()
        
        # notify listeners about the new dataset
        self.hub.onNewDataset(name, self.listeners)
        return dataset
        
    def openDataset(self, name):
        # first lookup by number if necessary
        if isinstance(name, (int, long)):
            for oldName in self.listDatasets():
                num = int(oldName[:5])
                if name == num:
                    name = oldName
                    break
        # if it's still a number, we didn't find the set
        if isinstance(name, (int, long)):
            raise DatasetNotFoundError(name)

        filename = dsEncode(name)
        if not os.path.exists(os.path.join(self.dir, filename + '.csv')):
            raise DatasetNotFoundError(name)

        if name in self.datasets:
            dataset = self.datasets[name]
            dataset.access()
        else:
            # need to create a new wrapper for this dataset
            dataset = Dataset(self, name)
            self.datasets[name] = dataset
        self.access()
        
        return dataset

    def updateTags(self, tags, sessions, datasets):
        def updateTagDict(tags, entries, d):
            updates = []
            for entry in entries:
                changed = False
                if entry not in d:
                    d[entry] = set()
                entryTags = d[entry]
                for tag in tags:
                    if tag[:1] == '-':
                        # remove this tag
                        tag = tag[1:]
                        if tag in entryTags:
                            entryTags.remove(tag)
                            changed = True
                    elif tag[:1] == '^':
                        # toggle this tag
                        tag = tag[1:]
                        if tag in entryTags:
                            entryTags.remove(tag)
                        else:
                            entryTags.add(tag)
                        changed = True
                    else:
                        # add this tag
                        if tag not in entryTags:
                            entryTags.add(tag)
                            changed = True
                if changed:
                    updates.append((entry, sorted(entryTags)))
            return updates

        sessUpdates = updateTagDict(tags, sessions, self.session_tags)
        dataUpdates = updateTagDict(tags, datasets, self.dataset_tags)

        self.access()
        if len(sessUpdates) + len(dataUpdates):
            # fire a message about the new tags
            msg = (sessUpdates, dataUpdates)
            self.hub.onTagsUpdated(msg, self.listeners)

    def getTags(self, sessions, datasets):
        sessTags = [(s, sorted(self.session_tags.get(s, []))) for s in sessions]
        dataTags = [(d, sorted(self.dataset_tags.get(d, []))) for d in datasets]
        return sessTags, dataTags

class Dataset(object):
    def __init__(self, session, name, title=None, num=None, create=False):
        self.hub = session.hub
        self.name = name
        file_base = os.path.join(session.dir, dsEncode(name))
        self.datafile = file_base + '.csv'
        self.infofile = file_base + '.ini'
        self.file # create the datafile, but don't do anything with it
        self.listeners = set() # contexts that want to hear about added data
        self.param_listeners = set()
        self.comment_listeners = set()
        
        if create:
            self.title = title
            self.created = self.accessed = self.modified = datetime.now()
            self.independents = []
            self.dependents = []
            self.parameters = []
            self.comments = []
            self.save()
        else:
            self.load()
            self.access()

    def load(self):
        S = DVSafeConfigParser()
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
        self.independents = [getInd(i) for i in range(count)]

        def getDep(i):
            sec = 'Dependent %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            units = S.get(sec, 'Units', raw=True)
            categ = S.get(sec, 'Category', raw=True)
            return dict(label=label, units=units, category=categ)
        count = S.getint(gen, 'Dependent')
        self.dependents = [getDep(i) for i in range(count)]

        def getPar(i):
            sec = 'Parameter %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            # TODO: big security hole! eval can execute arbitrary code
            data = T.evalLRData(S.get(sec, 'Data', raw=True))
            return dict(label=label, data=data)
        count = S.getint(gen, 'Parameters')
        self.parameters = [getPar(i) for i in range(count)]

        # get comments if they're there
        if S.has_section('Comments'):
            def getComment(i):
                sec = 'Comments'
                time, user, comment = eval(S.get(sec, 'c%d' % i, raw=True))
                return timeFromStr(time), user, comment
            count = S.getint(gen, 'Comments')
            self.comments = [getComment(i) for i in range(count)]
        else:
            self.comments = []
        
    def save(self):
        S = DVSafeConfigParser()
        
        sec = 'General'
        S.add_section(sec)
        S.set(sec, 'Created',  timeToStr(self.created))
        S.set(sec, 'Accessed', timeToStr(self.accessed))
        S.set(sec, 'Modified', timeToStr(self.modified))
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
            # TODO: smarter saving here, since eval'ing is insecure
            S.set(sec, 'Data', repr(par['data']))

        sec = 'Comments'
        S.add_section(sec)
        for i, (time, user, comment) in enumerate(self.comments):
            time = timeToStr(time)
            S.set(sec, 'c%d' % i, repr((time, user, comment)))
            
        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        """Update time of last access for this dataset."""
        self.accessed = datetime.now()
        self.save()

    @property
    def file(self):
        """Open the datafile on demand.

        The file is also scheduled to be closed
        if it has not accessed for a while.
        """
        if not hasattr(self, '_file'):
            self._file = open(self.datafile, 'a+') # append data
            self._fileTimeoutCall = callLater(FILE_TIMEOUT, self._fileTimeout)
        else:
            self._fileTimeoutCall.reset(FILE_TIMEOUT)
        return self._file
        
    def _fileTimeout(self):
        self._file.close()
        del self._file
        del self._fileTimeoutCall
    
    def _fileSize(self):
        """Check the file size of our datafile."""
        # does this include the size before the file has been flushed to disk?
        return os.fstat(self.file.fileno()).st_size
    
    @property
    def data(self):
        """Read data from file on demand.
        
        The data is scheduled to be cleared from memory unless accessed."""
        if not hasattr(self, '_data'):
            self._data = []
            self._datapos = 0
            self._dataTimeoutCall = callLater(DATA_TIMEOUT, self._dataTimeout)
        else:
            self._dataTimeoutCall.reset(DATA_TIMEOUT)
        f = self.file
        f.seek(self._datapos)
        lines = f.readlines()
        self._data.extend([float(n) for n in line.split(',')] for line in lines)
        self._datapos = f.tell()
        return self._data
    
    def _dataTimeout(self):
        del self._data
        del self._datapos
        del self._dataTimeoutCall
    
    def _saveData(self, data):
        f = self.file
        for row in data:
            # always save with dos linebreaks
            f.write(', '.join(DATA_FORMAT % v for v in row) + '\r\n')
        f.flush()
    
    def addIndependent(self, label):
        """Add an independent variable to this dataset."""
        if isinstance(label, tuple):
            label, units = label
        else:
            label, units = parseIndependent(label)
        d = dict(label=label, units=units)
        self.independents.append(d)
        self.save()

    def addDependent(self, label):
        """Add a dependent variable to this dataset."""
        if isinstance(label, tuple):
            label, legend, units = label
        else:
            label, legend, units = parseDependent(label)
        d = dict(category=label, label=legend, units=units)
        self.dependents.append(d)
        self.save()

    def addParameter(self, name, data, saveNow=True):
        self._addParam(name, data)
        if saveNow:
            self.save()
        
        # notify all listening contexts
        self.hub.onNewParameter(None, self.param_listeners)
        self.param_listeners = set()
        return name

    def addParameters(self, params, saveNow=True):
        for name, data in params:
            self._addParam(name, data)
        if saveNow:
            self.save()
        
        # notify all listening contexts
        self.hub.onNewParameter(None, self.param_listeners)
        self.param_listeners = set()
        
    def _addParam(self, name, data):
        for p in self.parameters:
            if p['label'] == name:
                raise ParameterInUseError(name)
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
        raise BadParameterError(name)
        
    def addData(self, data):
        varcount = len(self.independents) + len(self.dependents)
        if not len(data) or not isinstance(data[0], list):
            data = [data]
        if len(data[0]) != varcount:
            raise BadDataError(varcount, len(data[0]))
            
        # append the data to the file
        self._saveData(data)
        
        # notify all listening contexts
        self.hub.onDataAvailable(None, self.listeners)
        self.listeners = set()
    
    def getData(self, limit, start):
        if limit is None:
            data = self.data[start:]
        else:
            data = self.data[start:start+limit]
        return data, start + len(data)
        
    def keepStreaming(self, context, pos):
        if pos < len(self.data):
            if context in self.listeners:
                self.listeners.remove(context)
            self.hub.onDataAvailable(None, [context])
        else:
            self.listeners.add(context)
            
    def addComment(self, user, comment):
        self.comments.append((datetime.now(), user, comment))
        self.save()
        
        # notify all listening contexts
        self.hub.onCommentsAvailable(None, self.comment_listeners)
        self.comment_listeners = set()

    def getComments(self, limit, start):
        if limit is None:
            comments = self.comments[start:]
        else:
            comments = self.comments[start:start+limit]
        return comments, start + len(comments)
        
    def keepStreamingComments(self, context, pos):
        if pos < len(self.comments):
            if context in self.comment_listeners:
                self.comment_listeners.remove(context)
            self.hub.onCommentsAvailable(None, [context])
        else:
            self.comment_listeners.add(context)
        

class NumpyDataset(Dataset):

    def _get_data(self):
        """Read data from file on demand.
        
        The data is scheduled to be cleared from memory unless accessed."""
        if not hasattr(self, '_data'):
            try:
                # if the file is empty, this line can barf in certain versions
                # of numpy.  Clearly, if the file does not exist on disk, this
                # will be the case.  Even if the file exists on disk, we must
                # check its size
                if self._fileSize() > 0:
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
            self._dataTimeoutCall = callLater(DATA_TIMEOUT, self._dataTimeout)
        else:
            self._dataTimeoutCall.reset(DATA_TIMEOUT)
        return self._data

    def _set_data(self, data):
        self._data = data
        
    data = property(_get_data, _set_data)
    
    def _saveData(self, data):
        f = self.file
	# always save with dos linebreaks (requires numpy 1.5.0 or greater)
        np.savetxt(f, data, fmt=DATA_FORMAT, delimiter=',', newline='\r\n')
        f.flush()
    
    def _dataTimeout(self):
        del self._data
        del self._dataTimeoutCall
        
    def addData(self, data):
        varcount = len(self.independents) + len(self.dependents)
        data = data.asarray
        
        # reshape single row
        if len(data.shape) == 1:
            data.shape = (1, data.size)
        
        # check row length
        if data.shape[-1] != varcount:
            raise BadDataError(varcount, data.shape[-1])
        
        # append data to in-memory data
        if self.data.size > 0:
            self.data = np.vstack((self.data, data))
        else:
            self.data = data
            
        # append data to file
        self._saveData(data)
        
        # notify all listening contexts
        self.hub.onDataAvailable(None, self.listeners)
        self.listeners = set()
    
    def getData(self, limit, start):
        if limit is None:
            data = self.data[start:]
        else:
            data = self.data[start:start+limit]
        # nrows should be zero for an empty row
        nrows = len(data) if data.size > 0 else 0
        return data, start + nrows
        
    def keepStreaming(self, context, pos):
        # cheesy hack: if pos == 0, we only need to check whether
        # the filesize is nonzero
        if pos == 0:
            more = os.path.getsize(self.datafile) > 0
        else:
            nrows = len(self.data) if self.data.size > 0 else 0
            more = pos < nrows
        if more:
            if context in self.listeners:
                self.listeners.remove(context)
            self.hub.onDataAvailable(None, [context])
        else:
            self.listeners.add(context)
        
if useNumpy:
    Dataset = NumpyDataset


class DataVault(LabradServer):
    name = 'Data Vault'
    
    def __init__(self, host, port, password, hub, path):
        LabradServer.__init__(self)
        self.host = host
        self.port = port
        self.password = password
        self.hub = hub
        self.path = path
        self.onNewDir = Signal(543617, 'signal: new dir', 's')
        self.onNewDataset = Signal(543618, 'signal: new dataset', 's')
        self.onTagsUpdated = Signal(543622, 'signal: tags updated', '*(s*s)*(s*s)')

    # dataset signals
        self.onDataAvailable = Signal(543619, 'signal: data available', '')
        self.onNewParameter = Signal(543620, 'signal: new parameter', '')
        self.onCommentsAvailable = Signal(543621, 'signal: comments available', '')
    
    def initServer(self):
        # let the DataVaultHost know that we connected
        self.hub.connect(self)
        # create root session
        root = Session([''], self.hub)

    def initContext(self, c):
        # start in the root session
        c['path'] = ['']
        # start listening to the root session
        c['session'] = Session([''], self.hub)
        c['session'].listeners.add(ExtendedContext(self, c.ID))
        #print "Adding %s to listeners for %s" % (c.ID, [''])
        
    def expireContext(self, c):
        """Stop sending any signals to this context."""
        ctx = ExtendedContext(self, c.ID)
        def removeFromList(ls):
            if ctx in ls:
                ls.remove(ctx)
        for session in Session.getAll():
            removeFromList(session.listeners)
            for dataset in session.datasets.values():
                removeFromList(dataset.listeners)
                removeFromList(dataset.param_listeners)
                removeFromList(dataset.comment_listeners)
        
    def getSession(self, c):
        """Get a session object for the current path."""
        return c['session']
        #return Session(c['path'], self)

    def getDataset(self, c):
        """Get a dataset object for the current dataset."""
        if 'dataset' not in c:
            raise NoDatasetError()
        return c['datasetObj']
        #session = self.getSession(c)
        #return session.datasets[c['dataset']]

    # session signals
    #onNewDir = Signal(543617, 'signal: new dir', 's')
    #onNewDataset = Signal(543618, 'signal: new dataset', 's')
    #onTagsUpdated = Signal(543622, 'signal: tags updated', '*(s*s)*(s*s)')

    # dataset signals
    #onDataAvailable = Signal(543619, 'signal: data available', '')
    #onNewParameter = Signal(543620, 'signal: new parameter', '')
    #onCommentsAvailable = Signal(543621, 'signal: comments available', '')
    
    @setting(6, tagFilters=['s', '*s'], includeTags='b',
                returns=['*s{subdirs}, *s{datasets}',
                         '*(s*s){subdirs}, *(s*s){datasets}'])
    def dir(self, c, tagFilters=['-trash'], includeTags=None):
        """Get subdirectories and datasets in the current directory."""
        #print 'dir:', tagFilters, includeTags
        if isinstance(tagFilters, str):
            tagFilters = [tagFilters]
        sess = self.getSession(c)
        dirs, datasets = sess.listContents(tagFilters)
        if includeTags:
            dirs, datasets = sess.getTags(dirs, datasets)
        #print dirs, datasets
        return dirs, datasets
    
    @setting(7, path=['{get current directory}',
                      's{change into this directory}',
                      '*s{change into each directory in sequence}',
                      'w{go up by this many directories}'],
                create='b',
                returns='*s')
    def cd(self, c, path=None, create=False):
        """Change the current directory.
        
        The empty string '' refers to the root directory. If the 'create' flag
        is set to true, new directories will be created as needed.
        Returns the path to the new current directory.
        """
        if path is None:
            return c['path']
        #print "cd to path %s for %s %s" % (path, type(c), c.__dict__)
        temp = c['path'][:] # copy the current path
        if isinstance(path, (int, long)):
            if path > 0:
                temp = temp[:-path]
                if not len(temp):
                    temp = ['']
        else:
            if isinstance(path, str):
                path = [path]
            for dir in path:
                if dir == '':
                    temp = ['']
                else:
                    temp.append(dir)
                if not Session.exists(temp) and not create:
                    raise DirectoryNotFoundError(temp)
                session = Session(temp, self.hub) # touch the session
        if c['path'] != temp:
            # stop listening to old session and start listening to new session
            ctx = ExtendedContext(self, c.ID)
            #print "removing %s from session %s" % (ctx, c['path'])
            Session(c['path'], self.hub).listeners.remove(ctx)
            session = Session(temp, self.hub)
            #print "Adding %s to listeners for %s" % (ctx, temp)
            session.listeners.add(ctx)
            c['session'] = session
            c['path'] = temp
        return c['path']
        
    @setting(8, name='s', returns='*s')
    def mkdir(self, c, name):
        """Make a new sub-directory in the current directory.
        
        The current directory remains selected.  You must use the
        'cd' command to select the newly-created directory.
        Directory name cannot be empty.  Returns the path to the
        created directory.
        """
        if name == '':
            raise EmptyNameError()
        path = c['path'] + [name]
        if Session.exists(path):
            raise DirectoryExistsError(path)
        sess = Session(path, self.hub) # make the new directory
        return path
    
    @setting(9, name='s',
                independents=['*s', '*(ss)'],
                dependents=['*s', '*(sss)'],
                returns='(*s{path}, s{name})')
    def new(self, c, name, independents, dependents):
        """Create a new Dataset.

        Independent and dependent variables can be specified either
        as clusters of strings, or as single strings.  Independent
        variables have the form (label, units) or 'label [units]'.
        Dependent variables have the form (label, legend, units)
        or 'label (legend) [units]'.  Label is meant to be an
        axis label that can be shared among traces, while legend is
        a legend entry that should be unique for each trace.
        Returns the path and name for this dataset.
        """
        session = self.getSession(c)
        dataset = session.newDataset(name or 'untitled', independents, dependents)
        c['dataset'] = dataset.name # not the same as name; has number prefixed
        c['datasetObj'] = dataset
        c['filepos'] = 0 # start at the beginning
        c['commentpos'] = 0
        c['writing'] = True
        return c['path'], c['dataset']
    
    @setting(10, name=['s', 'w'], returns='(*s{path}, s{name})')
    def open(self, c, name):
        """Open a Dataset for reading.
        
        You can specify the dataset by name or number.
        Returns the path and name for this dataset.
        """
        session = self.getSession(c)
        dataset = session.openDataset(name)
        c['dataset'] = dataset.name # not the same as name; has number prefixed
        c['datasetObj'] = dataset
        c['filepos'] = 0
        c['commentpos'] = 0
        c['writing'] = False
        ctx = ExtendedContext(self, c.ID)
        dataset.keepStreaming(ctx, 0)
        dataset.keepStreamingComments(ctx, 0)
        return c['path'], c['dataset']
    
    @setting(20, data=['*v: add one row of data',
                       '*2v: add multiple rows of data'],
                 returns='')
    def add(self, c, data):
        """Add data to the current dataset.
        
        The number of elements in each row of data must be equal
        to the total number of variables in the data set
        (independents + dependents).
        """
        dataset = self.getDataset(c)
        if not c['writing']:
            raise ReadOnlyError()
        dataset.addData(data)

    @setting(21, limit='w', startOver='b', returns='*2v')
    def get(self, c, limit=None, startOver=False):
        """Get data from the current dataset.
        
        Limit is the maximum number of rows of data to return, with
        the default being to return the whole dataset.  Setting the
        startOver flag to true will return data starting at the beginning
        of the dataset.  By default, only new data that has not been seen
        in this context is returned.
        """
        dataset = self.getDataset(c)
        c['filepos'] = 0 if startOver else c['filepos']
        data, c['filepos'] = dataset.getData(limit, c['filepos'])
        ctx = ExtendedContext(self, c.ID)
        dataset.keepStreaming(ctx, c['filepos'])
        return data
    
    @setting(100, returns='(*(ss){independents}, *(sss){dependents})')
    def variables(self, c):
        """Get the independent and dependent variables for the current dataset.
        
        Each independent variable is a cluster of (label, units).
        Each dependent variable is a cluster of (label, legend, units).
        Label is meant to be an axis label, which may be shared among several
        traces, while legend is unique to each trace.
        """
        ds = self.getDataset(c)
        ind = [(i['label'], i['units']) for i in ds.independents]
        dep = [(d['category'], d['label'], d['units']) for d in ds.dependents]
        return ind, dep

    @setting(120, returns='*s')
    def parameters(self, c):
        """Get a list of parameter names."""
        dataset = self.getDataset(c)
        ctx = ExtendedContext(self, c)
        dataset.param_listeners.add(ctx) # send a message when new parameters are added
        return [par['label'] for par in dataset.parameters]

    @setting(121, 'add parameter', name='s', returns='')
    def add_parameter(self, c, name, data):
        """Add a new parameter to the current dataset."""
        dataset = self.getDataset(c)
        dataset.addParameter(name, data)

    @setting(122, 'get parameter', name='s')
    def get_parameter(self, c, name, case_sensitive=True):
        """Get the value of a parameter."""
        dataset = self.getDataset(c)
        return dataset.getParameter(name, case_sensitive)

    @setting(123, 'get parameters')
    def get_parameters(self, c):
        """Get all parameters.
        
        Returns a cluster of (name, value) clusters, one for each parameter.
        If the set has no parameters, nothing is returned (since empty clusters
        are not allowed).
        """
        dataset = self.getDataset(c)
        names = [par['label'] for par in dataset.parameters]
        params = tuple((name, dataset.getParameter(name)) for name in names)
        ctx = ExtendedContext(self, c.ID)
        dataset.param_listeners.add(ctx) # send a message when new parameters are added
        if len(params):
            return params

    @setting(124, 'add parameters', params='?{((s?)(s?)...)}', returns='')
    def add_parameters(self, c, params):
        """Add a new parameter to the current dataset."""
        dataset = self.getDataset(c)
        dataset.addParameters(params)

    @inlineCallbacks
    def read_pars_int(self, c, ctx, dataset, curdirs, subdirs=None):
        p = self.client.registry.packet(context=ctx)
        todo = []
        for curdir, curcontent in curdirs:
            if len(curdir) > 0:
                p.cd(curdir)
            for key in curcontent[1]:
                p.get(key, key=(False, tuple(curdir+[key])))
            if subdirs is not None:
                if isinstance(subdirs, list):
                    for folder in curcontent[0]:
                        if folder in subdirs:
                            p.cd(folder)
                            p.dir(key=(True, tuple(curdir+[folder])))
                            p.cd(1)
                elif subdirs != 0:
                    for folder in curcontent[0]:
                        p.cd(folder)
                        p.dir(key=(True, tuple(curdir+[folder])))
                        p.cd(1)                
            if len(curdir) > 0:
                p.cd(len(curdir))
        ans = yield p.send()
        if isinstance(subdirs, list):
            subdirs = -1
        else:
            if (subdirs is not None) and (subdirs > 0):
                subdirs -= 1
        for key in sorted(ans.settings.keys()):
            item = ans[key]
            if isinstance(key, tuple):
                if key[0]:
                    curdirs = [(list(key[1]), item)]
                    yield self.read_pars_int(c, ctx, dataset, curdirs, subdirs)
                else:
                    dataset.addParameter(' -> '.join(key[1]), item, saveNow=False)
        
        

    @setting(125, 'import parameters',
                  subdirs=[': Import current directory',
                           'w: Include this many levels of subdirectories (0=all)',
                           '*s: Include these subdirectories'],
                  returns='')
    def import_parameters(self, c, subdirs=None):
        """Reads all entries from the current registry directory, optionally
        including subdirectories, as parameters into the current dataset."""
        dataset = self.getDataset(c)
        ctx = self.client.context()
        p = self.client.registry.packet(context=ctx)
        p.duplicate_context(c.ID)
        p.dir()
        ans = yield p.send()
        curdirs = [([], ans.dir)]
        if subdirs == 0:
            subdirs = -1
        yield self.read_pars_int(c, ctx, dataset, curdirs, subdirs)
        dataset.save() # make sure the new parameters get saved
 
    @setting(126, 'get name', returns='s')
    def get_name(self, c):
        """Get the name of the current dataset."""
        dataset = self.getDataset(c)
        name = dataset.name
        return name

    @setting(200, 'add comment', comment='s', user='s', returns='')
    def add_comment(self, c, comment, user='anonymous'):
        """Add a comment to the current dataset."""
        dataset = self.getDataset(c)
        return dataset.addComment(user, comment)
        
    @setting(201, 'get comments', limit='w', startOver='b',
                                  returns='*(t, s{user}, s{comment})')
    def get_comments(self, c, limit=None, startOver=False):
        """Get comments for the current dataset."""
        dataset = self.getDataset(c)
        c['commentpos'] = 0 if startOver else c['commentpos']
        comments, c['commentpos'] = dataset.getComments(limit, c['commentpos'])
        ctx = ExtendedContext(self, c.ID)
        dataset.keepStreamingComments(ctx, c['commentpos'])
        return comments

    @setting(300, 'update tags', tags=['s', '*s'],
                  dirs=['s', '*s'], datasets=['s', '*s'],
                  returns='')
    def update_tags(self, c, tags, dirs, datasets=None):
        """Update the tags for the specified directories and datasets.

        If a tag begins with a minus sign '-' then the tag (everything
        after the minus sign) will be removed.  If a tag begins with '^'
        then it will be toggled from its current state for each entry
        in the list.  Otherwise it will be added.

        The directories and datasets must be in the current directory.
        """
        if isinstance(tags, str):
            tags = [tags]
        if isinstance(dirs, str):
            dirs = [dirs]
        if datasets is None:
            datasets = [self.getDataset(c)]
        elif isinstance(datasets, str):
            datasets = [datasets]
        sess = self.getSession(c)
        sess.updateTags(tags, dirs, datasets)

    @setting(301, 'get tags',
                  dirs=['s', '*s'], datasets=['s', '*s'],
                  returns='*(s*s)*(s*s)')
    def get_tags(self, c, dirs, datasets):
        """Get tags for directories and datasets in the current dir."""
        sess = self.getSession(c)
        if isinstance(dirs, str):
            dirs = [dirs]
        if isinstance(datasets, str):
            datasets = [datasets]
        return sess.getTags(dirs, datasets)

    @setting(401, 'get servers', returns='*(swb)')
    def get_servers(self, c):
        """
        Returns the list of running servers as tuples of (host, port, connected?)
        """
        rv = []
        for s in self.hub:
            host = s.host
            port = s.port
            running = hasattr(s, 'cxn') and bool(s.cxn)
            print "host: %s port: %s running: %s" % (host, port, running)
            rv.append((host, port, running))
        return rv

    @setting(402, 'add server', host=['s'], port=['w'], password=['s'])
    def add_server(self, c, host, port=0, password=None):
        """
        Add new server to the list.
        """
        port = port or self.port
        password = password or self.password
        self.hub.addService(DataVaultConnector(host, port, password, self.hub))
    
class DataVaultConnector(MultiService):
    """Service that connects the Data Vault to a single LabRAD manager
    
    If the manager is stopped or we lose the network connection,
    this service attempts to reconnect so that we will come
    back online when the manager is back up.
    """
    reconnectDelay = 10
    
    def __init__(self, host, port, password, hub, path):
        MultiService.__init__(self)
        self.host = host
        self.port = port
        self.password = password
        self.hub = hub
        self.path = path
        
    def startService(self):
        MultiService.startService(self)
        self.startConnection()

    def startConnection(self):
        """Attempt to start the data vault and connect to LabRAD."""
        print 'Connecting to %s:%d...' % (self.host, self.port)
        self.server = DataVault(self.host, self.port, self.password, self.hub, self.path)
        self.server.onStartup().addErrback(self._error)
        self.server.onShutdown().addCallbacks(self._disconnected, self._error)
        self.cxn = TCPClient(self.host, self.port, self.server)
        self.addService(self.cxn)
        
    def _disconnected(self, data):
        print 'Disconnected from %s:%d.' % (self.host, self.port)
        self.hub.disconnect(self.server)
        return self._reconnect()

    def _error(self, failure):
        print failure.getErrorMessage()
        self.hub.disconnect(self.server)
        return self._reconnect()

    def _reconnect(self):
        """Clean up from the last run and reconnect."""
        ## hack: manually clearing the dispatcher...
        #dispatcher.connections.clear()
        #dispatcher.senders.clear()
        #dispatcher._boundMethods.clear()
        ## end hack
        if hasattr(self, 'cxn'):
            self.removeService(self.cxn)
            del self.cxn
        reactor.callLater(self.reconnectDelay, self.startConnection)
        print 'Will try to reconnect to %s:%d in %d seconds...' % (self.host, self.port, self.reconnectDelay)
    
class DataVaultServiceHost(MultiService):
    """Parent Service that manages multiple child DataVaultConnector's"""
    
    signals = [
        'onNewDir',
        'onNewDataset',
        'onTagsUpdated',
        'onDataAvailable',
        'onNewParameter',
        'onCommentsAvailable'
    ]
    
    def __init__(self, path, managers):
        MultiService.__init__(self)
        self.path = path        
        self.managers = managers
        self.servers = set()
        for signal in self.signals:
            self.wrapSignal(signal)
        for host, port, password in managers:
            self.addService(DataVaultConnector(host, port, password, self, self.path))
    
    def connect(self, server):
        print 'server connected: %s:%d' % (server.host, server.port)
        self.servers.add(server)
    
    def disconnect(self, server):
        print 'server disconnected: %s:%d' % (server.host, server.port)
        if server in self.servers:
            self.servers.remove(server)
    
    def __str__(self):
        managers = ['%s:%d' % (m[0], m[1]) for m in self.managers]
        return 'DataVaultServiceHost(%s)' % (managers,) 
    
    def wrapSignal(self, signal):
        print 'wrapping signal:', signal
        def relay(data, contexts=None, tag=None):
            for c in contexts:
                try:
                    sig = getattr(c.server, signal)
                    sig(data, [c.context], tag)
                except Exception as e:
                    print 'error relaying signal %s to %s:%s: %s' % (signal, c.server.host, c.server.port, e)
        setattr(self, signal, relay)

def load_settings():
    '''
    Make a client connection to the labrad host specified in the
    environment (i.e., by the node server) and load the rest of the settings
    from there.

    This file also takes care of locking the datavault storage directory.
    The lock only works on the local host, so we also node lock the datavault:
    if the registry has a 'Node' key, the datavault will refuse to start
    on any other host.  This should prevent ever having two copies of the
    datavault running.
    '''
    cxn = labrad.connect()
    reg = cxn.registry
    path = ['', 'Servers', 'Data Vault', 'Multihead']
    reg = cxn.registry
    # try to load for this node
    p = reg.packet()
    p.cd(path)
    p.get("Repository", 's', key="repo")
    p.get("Managers", "*(sws)", key="managers")
    p.get("Node", "s", False, "", key="node")
    ans = p.send(wait=True)
    if ans.node and (ans.node != util.getNodeName()):
        raise RuntimeError("Node name %s from registry does not match current host %s" % (ans.node, util.getNodeName()))
    lock_path(ans.repo)
    cxn.disconnect()
    return ans.repo, ans.managers
        
def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--auto':
        path, managers = load_settings()
    else:
        if len(sys.argv) < 3:
            print 'usage: %s /path/to/vault/directory [password@]host[:port] [password2]@host2[:port2] ...' % (sys.argv[0])
            sys.exit(1)
        path = sys.argv[1]
        # We lock the datavault path, but we can't check the node lock unless using
        # --auto to get the data from the registry.
        lock_path(ans.repo)
        manager_list = sys.argv[2:]
        managers = []
        for m in manager_list:
            password, sep, hostport = m.rpartition('@')
            host, sep, port = hostport.partition(':')
            if sep == '':
                port = 0
            else:
                port = int(port)
            managers.append((host, port, password))
    
    global DATADIR
    DATADIR = path
    if not os.path.exists(path):
        raise Exception('data path %s does not exist' % path)
    if not os.path.isdir(path):
        raise Exception('data path %s is not a directory' % path)
        sys.exit()

    def parseManagerInfo(manager):
        host, port, password = manager
        if not password:
            password = constants.PASSWORD
        if not port:
            port = constants.MANAGER_PORT
        return (host, port, password)
    managers = [parseManagerInfo(m) for m in managers]
    service = DataVaultServiceHost(path, managers)
    service.startService()
    if labrad.thread._reactorThread:
        # If we created a client connection to get registry data, the reactor is already running
        # in a separate thread.  We can't restart the reactor in the main thread, so we just wait.
        # We don't use join() because it can't be interrupted by a keyboard event.
        #
        # For some reason, when the reactor is run in a separate thread, it takes ~10 seconds to
        # make the initial server connections.  The right way to do this is to have the auto-load
        # code be executed from the reactor, and then start up the servers, but I don't know how
        # to do that.
        while(True):
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                reactor.stop()
                raise
    else:
        reactor.run()
if __name__ == '__main__':
    main()
