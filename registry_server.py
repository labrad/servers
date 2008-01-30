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
from labrad.server import LabradServer, setting

import os

# look for a configuration file in this directory
cf = ConfigFile('registry_server', os.path.split(__file__)[0])
DATADIR = cf.get('config', 'repository')


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
    return os.path.join(DATADIR, *[dsEncode(d) for d in path])

def keyfile(path, key):
    return os.path.join(filedir(path), dsEncode(key) + '.key')
    

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


class RegistryServer(LabradServer):
    name = 'Registry'

    def initServer(self):
        self.defaultCtxtData['path'] = ['']

    @setting(1, returns=['(*s{subdirectories}, *s{keys})'])
    def dir(self, c):
        """Get subdirectories and keys in the current directory."""
        path = filedir(c['path'])
        files = os.listdir(path)
        dirs = [dsDecode(f) for f in files
                            if os.path.isdir(os.path.join(path, f))]
        keys = [dsDecode(f[:-4]) for f in files
                                 if f.endswith('.key') and
                                    os.path.isfile(os.path.join(path, f))]
        return dirs, keys
        
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
        
        if isinstance(path, (int, long)):
            if path > 0:
                c['path'] = c['path'][:-path]
                if not len(c['path']):
                    c['path'] = ['']
            return c['path']
        
        temp = c['path'][:] # copy the current path
        if isinstance(path, str):
            path = [path]
        for dir in path:
            if dir == '':
                temp = ['']
            else:
                temp.append(dir)
            fpath = filedir(temp)
            if not os.path.exists(fpath):
                if create:
                    os.makedirs(fpath)
                else:
                    raise DirectoryNotFoundError(temp)
        c['path'] = temp
        return c['path']

    @setting(15, name=['s'], returns=['*s'])
    def mkdir(self, c, name):
        """Make a new sub-directory in the current directory."""
        if name == '':
            raise EmptyNameError()
        path = c['path'] + [name]
        if os.path.exists(filedir(path)):
            raise DirectoryExistsError(path)
        os.makedirs(filedir(path))
        return path

    @setting(20, key=['s'])
    def get(self, c, key):
        """Get the contents of the specified key."""
        if key == '':
            raise EmptyNameError()
        fname = keyfile(c['path'], key)
        if not os.path.exists(fname):
            raise KeyNotFoundError(key)
        with open(fname, 'r') as f:
            return T.evalLRData(f.read())

    @setting(21, key=['s'], returns=['s'])
    def set(self, c, key, data):
        """Set the contents of the specified key."""
        if key == '':
            raise EmptyNameError()
        fname = keyfile(c['path'], key)        
        with open(fname, 'w') as f:
            f.write(repr(data))

    @setting(25, 'delete', key=['s'], returns = [''])
    def delete(self, c, key):
        """Deletes a key"""
        if key == '':
            raise EmptyNameError()
        fname = keyfile(c['path'], key)
        if not os.path.exists(fname):
            raise KeyNotFoundError(key)
        os.remove(fname)


__server__ = RegistryServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
