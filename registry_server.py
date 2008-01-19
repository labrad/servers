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

from labrad import types as T
from labrad.config import ConfigFile
from labrad.server import LabradServer, setting

import os

# look for a configuration file in this directory
cf = ConfigFile('registry_server', os.path.split(__file__)[0])
DATADIR = cf.get('config', 'repository')

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
    for char, code in encodings[1:] + encodings[0:1]:
        name = name.replace(code, char)
    return name

def makePath(dir):
    return '\\'.join([DATADIR] + [dsEncode(d) for d in dir])+'\\'


class DirectoryNotFoundError(T.Error):
    code = 1
    def __init__(self, name):
        self.msg="Directory '%s' not found!" % name

class DirectoryExistsError(T.Error):
    code = 2
    def __init__(self, name):
        self.msg="Directory '%s' already exists!" % name

class EmptyNameError(T.Error):
    """Names of directories or keys cannot be empty"""
    code = 3

class KeyNotFoundError(T.Error):
    code = 4
    def __init__(self, name):
        self.msg="Key '%s' not found!" % name


class RegistryServer(LabradServer):
    name = 'Registry'

    def initServer(self):
        self.defaultCtxtData['dir'] = []

    @setting(1, 'list keys', returns=['*s'])
    def list_keys(self, c):
        path = makePath(c['dir'])
        return [dsDecode(f[:-4]) for f in os.listdir(path)
                                 if f.endswith('.key') and
                                    os.path.isfile(path+f)]

    @setting(2, 'list directories', returns=['*s'])
    def list_dirs(self, c):
        path = makePath(c['dir'])
        return [dsDecode(f) for f in os.listdir(path)
                            if os.path.isdir(path+f)]

    @setting(10, 'change directory',
             newdir=[' : print current working directory',
                     's: change into this directory',
                     '*s: change into these directories starting from root',
                     'w: go up by this many directories'],
             returns=['s'])
    def chdir(self, c, newdir):
        """Changes the current working directory"""
        if newdir is None:
            return makePath(c['dir'])
        
        if isinstance(newdir, list):
            if '' in newdir:
                raise EmptyNameError()
            path = makePath(newdir)
            if not os.path.exists(path):
                raise DirectoryNotFoundError(path)
            c['dir'] = newdir
            return path

        if isinstance(newdir, long):
            if newdir > 0:
                c['dir'] = c['dir'][:-newdir]
            return makePath(c['dir'])

        if newdir=='':
            raise EmptyNameError()
        
        path = makePath(c['dir'] + [newdir])
        if not os.path.exists(path):
            raise DirectoryNotFoundError(path)
        
        c['dir'] = c['dir'] + [newdir]
        return path

    @setting(15, 'make directory', newdir=['s'], returns=['s'])
    def mkdir(self, c, newdir):
        """Creates a new directory"""
        if newdir=='':
            raise EmptyNameError()

        path = makePath(c['dir']) + dsEncode(newdir)
        if os.path.exists(path):
            raise DirectoryExistsError(path)

        os.makedirs(path)
        return path

    @setting(16, 'force directory',
             newdir=['s: change into this directory',
                     '*s: change into these directories starting from root'],
             returns=['s'])
    def forcedir(self, c, newdir):
        """Changes the current working directory, creating new directories as needed"""
        if isinstance(newdir, list):
            if '' in newdir:
                raise EmptyNameError()
            c['dir'] = newdir
            path = makePath(c['dir'])
            if not os.path.exists(path):
                os.makedirs(path)
            return path

        if newdir=='':
            raise EmptyNameError()

        c['dir'] = c['dir'] + [newdir]
        
        path = makePath(c['dir'])
        if not os.path.exists(path):
            os.makedirs(path)

        return path

    @setting(20, 'get key', key=['s'])
    def getkey(self, c, key):
        """Gets the contents of the key"""
        if key=='':
            raise EmptyNameError()
        
        fname = makePath(c['dir']) + dsEncode(key) + '.key'

        if not os.path.exists(fname):
            raise KeyNotFoundError(key)

        f = open(fname, 'r')
        data = f.read()
        f.close()

        return T.evalLRData(data)

    @setting(21, 'set key', key=['s'], returns=['s'])
    def setkey(self, c, key, data):
        """Sets the contents of the key"""
        if key=='':
            raise EmptyNameError()
        
        fname = makePath(c['dir']) + dsEncode(key) + '.key'

        f = open(fname, 'w')
        f.write(repr(data))
        f.close()

        return fname

    @setting(25, 'delete key', key=['s'], returns = [''])
    def delkey(self, c, key):
        """Deletes a key"""
        if key=='':
            raise EmptyNameError()
        
        fname = makePath(c['dir']) + dsEncode(key) + '.key'

        if not os.path.exists(fname):
            raise KeyNotFoundError(key)

        os.remove(fname)
        
        return


__server__ = RegistryServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
