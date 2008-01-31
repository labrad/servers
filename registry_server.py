#!c:\python25\python.exe

# Copyright (C) 2007  Markus Ansmann
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

from labrad import types as T
from labrad.config import ConfigFile
from labrad.server import LabradServer, setting, Signal

from ConfigParser import SafeConfigParser
from datetime import datetime
import os

# look for a configuration file in this directory
cf = ConfigFile('registry_server', os.path.split(__file__)[0])
DATADIR = cf.get('config', 'repository')
TIME_FORMAT = '%Y-%m-%d, %H:%M:%S'

## filename translation

encodings = [
    ('%', '%p'),
    ('/', '%f'),
    ('\\','%b'),
    (':', '%c'),
    ('*', '%a'),
    ('?', '%q'),
    ('"', '%Q'),
    ('<', '%l'),
    ('>', '%g'),
    ('|', '%P'),
    ('.', '%d'),
]

def dsEncode(name):
    for char, code in encodings:
        name = name.replace(char, code)
    return name

def dsDecode(name):
    for char, code in encodings[1:] + encodings[:1]:
        name = name.replace(code, char)
    return name

def filedir(path):
    return os.path.join(DATADIR, *[dsEncode(d) + '.dir' for d in path[1:]])

def keyfile(path, key):
    return os.path.join(filedir(path), dsEncode(key) + '.ini')


## time formatting
    
def timeToStr(t):
    return t.strftime(TIME_FORMAT)

def timeFromStr(s):
    return datetime.strptime(s, TIME_FORMAT)
    

## error messages

class DirectoryNotFoundError(T.Error):
    code = 1
    def __init__(self, name):
        self.msg = "Directory '%s' not found!" % name

class DirectoryExistsError(T.Error):
    code = 2
    def __init__(self, name):
        self.msg = "Directory '%s' already exists!" % name

class EmptyNameError(T.Error):
    """Names of directories or keys cannot be empty"""
    code = 3

class KeyNotFoundError(T.Error):
    code = 4
    def __init__(self, name):
        self.msg = "Key '%s' not found!" % name


class Directory(object):
    """Stores information about a directory on disk.
    
    One directory object is created for each data directory accessed.
    The directory object manages reading from and writing to the config
    file, and manages the keys in this directory.
    """
    
    # feep a dictionary of all created directory objects
    _dirs = {}
    
    @staticmethod
    def exists(path):
        """Check whether a directory exists on disk for a given path.
        
        This does not tell us whether a directory object has been
        created for that path.
        """
        return os.path.exists(filedir(path))
    
    def __new__(cls, path, parent):
        """Get a Directory object.
        
        If a directory already exists for the given path, return it.
        Otherwise, create a new directory instance.
        """
        path = tuple(path)
        if path in cls._dirs:
            return cls._dirs[path]
        inst = super(Directory, cls).__new__(cls)
        inst._init(path, parent)
        cls._dirs[path] = inst
        return inst

    def _init(self, path, parent):
        """Initialization that happens once when directory object is created."""
        self.path = path
        self.parent = parent
        self.dir = filedir(path)
        self.infofile = os.path.join(self.dir, 'directory.info')
        self.listeners = set()
        self.keys = {}

        if not os.path.exists(self.dir):
            os.makedirs(self.dir)
            
            # notify listeners about this new directory
            parent_dir = Directory(path[:-1], parent)
            parent.onNewDir(path[-1], list(parent_dir.listeners))
           
        if os.path.exists(self.infofile):
            self.load()
        else:
            self.created = self.modified = datetime.now()

        self.access() # update current access time and save
            
    def load(self):
        """Load info from the directory.info file."""
        S = SafeConfigParser()
        S.read(self.infofile)

        sec = 'Information'
        self.created = timeFromStr(S.get(sec, 'Created'))
        self.accessed = timeFromStr(S.get(sec, 'Accessed'))
        self.modified = timeFromStr(S.get(sec, 'Modified'))

    def save(self):
        """Save info to the directory.ini file."""
        S = SafeConfigParser()

        sec = 'Information'
        S.add_section(sec)
        S.set(sec, 'Created',  timeToStr(self.created))
        S.set(sec, 'Accessed', timeToStr(self.accessed))
        S.set(sec, 'Modified', timeToStr(self.modified))

        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        """Update last access time and save."""
        self.accessed = datetime.now()
        self.save()

    def listContents(self):
        """Get a list of directory names in this directory."""
        files = os.listdir(self.dir)
        dirs = [dsDecode(s[:-4]) for s in files if s.endswith('.dir')]
        keys = [dsDecode(s[:-4]) for s in files if s.endswith('.ini')]
        return dirs, keys
            
    def listKeys(self):
        """Get a list of dataset names in this directory."""
        files = os.listdir(self.dir)
        return [dsDecode(s[:-4]) for s in files if s.endswith('.ini')]
    
    def __getitem__(self, key):
        if key == '':
            raise EmptyNameError()
        fname = keyfile(self.path, key)
        if not os.path.exists(fname):
            raise KeyNotFoundError(key)
        with open(fname, 'r') as f:
            return T.evalLRData(f.read())
        
    def __delitem__(self, key):
        if key == '':
            raise EmptyNameError()
        fname = keyfile(self.path, key)
        if not os.path.exists(fname):
            raise KeyNotFoundError(key)
        os.remove(fname)
    
    def __setitem__(self, key, value):
        if key == '':
            raise EmptyNameError()
        fname = keyfile(self.path, key)        
        with open(fname, 'w') as f:
            f.write(T.reprLRData(value))
    
        #keyobj = Key(self, key)
        #self.keys[key] = keyobj
    
        self.modified = datetime.now()
        self.access()
        
        # notify listeners about the new key
        self.parent.onNewKey(key, list(self.listeners))


class Key:
    def __init__(self, directory, name, title=None, num=None, create=False):
        self.parent = directory.parent
        self.name = name
        file_base = os.path.join(directory.dir, dsEncode(name))
        self.infofile = file_base + '.ini'
        
        if create:
            self.title = title
            self.created = self.accessed = self.modified = datetime.now()
            self.parameters = []
            self.save()
        else:
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

        def getPar(i):
            sec = 'Parameter %d' % (i+1)
            label = S.get(sec, 'Label', raw=True)
            # TODO: big security hole! eval can execute arbitrary code
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
        S.set(sec, 'Independent', repr(len(self.independents)))
        S.set(sec, 'Dependent',   repr(len(self.dependents)))
        S.set(sec, 'Parameters',  repr(len(self.parameters)))

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

        with open(self.infofile, 'w') as f:
            S.write(f)

    def access(self):
        """Update time of last access for this dataset."""
        self.accessed = datetime.now()
        self.save()

    def addParameter(self, name, data):
        for p in self.parameters:
            if p['label'] == name:
                raise ParameterInUseError(name)
        d = dict(label=name, data=data)
        self.parameters.append(d)
        self.save()
        return name

    def getParameter(self, name):
        for p in self.parameters:
            if p['label'] == name:
                return p['data']
        raise BadParameterError(name)
        
    def addData(self, data):
        varcount = len(self.independents) + len(self.dependents)
        if not len(data) or not isinstance(data[0], list):
            data = [data]
        if len(data[0]) != varcount:
            raise BadDataError(varcount)
            
        # append the data to the file
        f = self.file
        for row in data:
            f.write(', '.join('%.*G' % (PRECISION, v) for v in row) + '\n')
        f.flush()
        
        # notify all listening contexts
        self.parent.onNewData(None, list(self.listeners))
        self.listeners = set()
        return f.tell()
        
    def getData(self, limit, start):
        if limit is None:
            data = self.data[start:]
        else:
            data = self.data[start:start+limit]
        return data, start + len(data)
        
        
class RegistryServer(LabradServer):
    name = 'Registry'

    def initServer(self):
        root = Directory([''], self) # create root directory

    def initContext(self, c):
        c['path'] = ['']
        Directory([''], self).listeners.add(c.ID) # start listening to the root directory
        
    def getDir(self, c):
        """Get a directory object for the current path."""
        return Directory(c['path'], self)
    
    onNewDir = Signal(543617, 'signal: new dir', 's')
    onNewKey = Signal(543618, 'signal: new key', 's')
    #onNewData = Signal(543619, 'signal: new data', '')
    
    @setting(1, returns=['(*s{subdirectories}, *s{keys})'])
    def dir(self, c):
        """Get subdirectories and keys in the current directory."""
        return self.getDir(c).listContents()
        
    @setting(10, path=['{get current directory}',
                       's{change into this directory}',
                       '*s{change into these directories starting from root}',
                       'w{go up by this many directories}'],
                 create=['b'],
                 returns=['*s'])
    def cd(self, c, path=None, create=False):
        """Change the current directory.
        
        The empty string '' refers to the root directory. If the 'create' flag
        is set to true, new directories will be created as needed.
        Returns the path to the new current directory.
        """
        if path is None:
            return c['path']
        
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
                if not Directory.exists(temp) and not create:
                    raise DirectoryNotFoundError(temp)
                session = Directory(temp, self) # touch the directory
        if c['path'] != temp:
            # stop listening to old directory and start listening to new directory
            Directory(c['path'], self).listeners.remove(c.ID)
            Directory(temp, self).listeners.add(c.ID)
            c['path'] = temp
        return c['path']

    @setting(15, name=['s'], returns=['*s'])
    def mkdir(self, c, name):
        """Make a new sub-directory in the current directory."""
        if name == '':
            raise EmptyNameError()
        path = c['path'] + [name]
        if Directory.exists(path):
            raise DirectoryExistsError(path)
        sess = Directory(path, self) # make the new directory
        return path

    @setting(20, key=['s'])
    def get(self, c, key):
        """Get the contents of the specified key."""
        return self.getDir(c)[key]

    @setting(21, key=['s'], returns=[''])
    def set(self, c, key, value):
        """Set the contents of the specified key."""
        self.getDir(c)[key] = value

    @setting(25, 'delete', key=['s'], returns = [''])
    def delete(self, c, key):
        """Deletes a key"""
        del self.getDir(c)[key]


__server__ = RegistryServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
