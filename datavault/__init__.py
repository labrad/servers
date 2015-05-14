import base64
from datetime import datetime
import os
import re
import weakref

from labrad import types as T

from . import backend, errors, util


## Filename translation.

_encodings = [
    ('%','%p'), # this one MUST be first for encode/decode to work properly
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

def filename_encode(name):
    """Encode special characters to produce a name that can be used as a filename"""
    for char, code in _encodings:
        name = name.replace(char, code)
    return name

def filename_decode(name):
    """Decode a string that has been encoded using filename_encode"""
    for char, code in _encodings[1:] + _encodings[0:1]:
        name = name.replace(code, char)
    return name

def filedir(datadir, path):
    return os.path.join(datadir, *[filename_encode(d) + '.dir' for d in path[1:]])


## time formatting

TIME_FORMAT = '%Y-%m-%d, %H:%M:%S'

def time_to_str(t):
    return t.strftime(TIME_FORMAT)

def time_from_str(s):
    return datetime.strptime(s, TIME_FORMAT)


## variable parsing

_re_label = re.compile(r'^([^\[(]*)') # matches up to the first [ or (
_re_legend = re.compile(r'\((.*)\)') # matches anything inside ( )
_re_units = re.compile(r'\[(.*)\]') # matches anything inside [ ]

def _get_match(pat, s, default=None):
    matches = re.findall(pat, s)
    if len(matches) == 0:
        if default is None:
            raise Exception("Cannot parse '{0}'.".format(s))
        return default
    return matches[0].strip()

def parse_independent(s):
    label = _get_match(_re_label, s)
    units = _get_match(_re_units, s, '')
    return label, units

def parse_dependent(s):
    label = _get_match(_re_label, s)
    legend = _get_match(_re_legend, s, '')
    units = _get_match(_re_units, s, '')
    return label, legend, units


## data-url support for storing parameters

DATA_URL_PREFIX = 'data:application/labrad;base64,'


class SessionStore(object):
    def __init__(self, datadir, hub):
        self._sessions = weakref.WeakValueDictionary()
        self.datadir = datadir
        self.hub = hub

    def get_all(self):
        return self._sessions.values()

    def exists(self, path):
        """Check whether a session exists on disk for a given path.

        This does not tell us whether a session object has been
        created for that path.
        """
        return os.path.exists(filedir(self.datadir, path))

    def get(self, path):
        """Get a Session object.

        If a session already exists for the given path, return it.
        Otherwise, create a new session instance.
        """
        path = tuple(path)
        if path in self._sessions:
            return self._sessions[path]
        session = Session(self.datadir, path, self.hub, self)
        self._sessions[path] = session
        return session


class Session(object):
    """Stores information about a directory on disk.

    One session object is created for each data directory accessed.
    The session object manages reading from and writing to the config
    file, and manages the datasets in this directory.
    """

    def __init__(self, datadir, path, hub, session_store):
        """Initialization that happens once when session object is created."""
        self.path = path
        self.hub = hub
        self.dir = filedir(datadir, path)
        self.infofile = os.path.join(self.dir, 'session.ini')
        self.datasets = weakref.WeakValueDictionary()

        if not os.path.exists(self.dir):
            os.makedirs(self.dir)

            # notify listeners about this new directory
            parent_session = session_store.get(path[:-1])
            hub.onNewDir(path[-1], parent_session.listeners)

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
        S = util.DVSafeConfigParser()
        S.read(self.infofile)

        sec = 'File System'
        self.counter = S.getint(sec, 'Counter')

        sec = 'Information'
        self.created = time_from_str(S.get(sec, 'Created'))
        self.accessed = time_from_str(S.get(sec, 'Accessed'))
        self.modified = time_from_str(S.get(sec, 'Modified'))

        # get tags if they're there
        if S.has_section('Tags'):
            self.session_tags = eval(S.get('Tags', 'sessions', raw=True))
            self.dataset_tags = eval(S.get('Tags', 'datasets', raw=True))
        else:
            self.session_tags = {}
            self.dataset_tags = {}

    def save(self):
        """Save info to the session.ini file."""
        S = util.DVSafeConfigParser()

        sec = 'File System'
        S.add_section(sec)
        S.set(sec, 'Counter', repr(self.counter))

        sec = 'Information'
        S.add_section(sec)
        S.set(sec, 'Created',  time_to_str(self.created))
        S.set(sec, 'Accessed', time_to_str(self.accessed))
        S.set(sec, 'Modified', time_to_str(self.modified))

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
        dirs = [filename_decode(s[:-4]) for s in files if s.endswith('.dir')]
        datasets = [filename_decode(s[:-4]) for s in files if s.endswith('.csv') or s.endswith('.bin')]
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
        return [filename_decode(s[:-4]) for s in files if s.endswith('.csv') or s.endswith('.bin')]

    def newDataset(self, title, independents, dependents):
        num = self.counter
        self.counter += 1
        self.modified = datetime.now()

        name = '%05d - %s' % (num, title)
        dataset = Dataset(self, name, title, create=True, independents=independents, dependents=dependents)
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
            raise errors.DatasetNotFoundError(name)

        filename = filename_encode(name)
        file_base = os.path.join(self.dir, filename)
        if not (os.path.exists(file_base + '.csv') or os.path.exists(file_base + '.bin')):
            raise errors.DatasetNotFoundError(name)

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
    def __init__(self, session, name, title=None, num=None, create=False, independents=[], dependents=[]):
        self.hub = session.hub
        self.name = name
        file_base = os.path.join(session.dir, filename_encode(name))
        self.infofile = file_base + '.ini'
        self.listeners = set() # contexts that want to hear about added data
        self.param_listeners = set()
        self.comment_listeners = set()

        if create:
            self.title = title
            self.created = self.accessed = self.modified = datetime.now()
            self.independents = [self.makeIndependent(i) for i in independents]
            self.dependents = [self.makeDependent(d) for d in dependents]
            self.parameters = []
            self.comments = []
            self.save()
        else:
            self.load()
            self.access()

        self.data = backend.create_backend(file_base, cols=len(self.independents) + len(self.dependents))

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
                try:
                    data = T.evalLRData(raw)
                except RuntimeError:
                    if raw.endswith('None)'):
                        data = T.evalLRData(raw[0:-5] + '"")')
                    else:
                        raise
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

    def access(self):
        """Update time of last access for this dataset."""
        self.accessed = datetime.now()
        self.save()

    def makeIndependent(self, label):
        """Add an independent variable to this dataset."""
        if isinstance(label, tuple):
            label, units = label
        else:
            label, units = parse_independent(label)
        return dict(label=label, units=units)

    def makeDependent(self, label):
        """Add a dependent variable to this dataset."""
        if isinstance(label, tuple):
            label, legend, units = label
        else:
            label, legend, units = parse_dependent(label)
        return dict(category=label, label=legend, units=units)

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

    def addData(self, data):
        # append the data to the file
        self.data.addData(data)

        # notify all listening contexts
        self.hub.onDataAvailable(None, self.listeners)
        self.listeners = set()

    def getData(self, limit, start):
        return self.data.getData(limit, start)

    def keepStreaming(self, context, pos):
        # keepStreaming does something a bit odd and has a confusing name (ERJ)
        #
        # The goal is this: a client that is listening for "new data" events should only
        # receive a single notification even if there are multiple writes.  To do this,
        # we do the following:
        #
        # If a client reads to the end of the dataset, it is added to the list to be notified
        # if another context does 'addData'.
        #
        # if a client calls 'addData', all listeners are notified, and then the set of listeners
        # is cleared.
        # 
        # If a client reads, but not to the end of the dataset, it is immediately notified that
        # there is more data for it to read, and then removed from the set of notifiers.
        if self.data.hasMore(pos):
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

