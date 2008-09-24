# Copyright (C) 2008  Max Hofheinz
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

import string

STR2IDENTIFIER = ''.join(chr(i) if chr(i) in (string.letters + string.digits) else '_' for i in range(256))

def str2identifier(s):
    s = s.translate(STR2IDENTIFIER)
    if s[0] in string.digits:
        s = '_' + s
    return s

def identifier2str(s):
    s = ''.join(' ' if i == '_' else i for i in s)
    return s.strip()
    

class dictclass(dict):

    def __getattr__(self, name):
        if dict.__contains__(self, name):
            return dict.__getitem__(self, identifier2str(name))
        else:
            raise AttributeError, name

    def __setattr__(self, name, value):
        dict.__setitem__(self, identifier2str(name), value)

    def _get_dict(self):
        return dict(self)

    __dict__ = property(_get_dict)

    def copy(self):
        return dictclass(dict.copy(self))

class RegistryWrapper(object):

    """Wrapper around the labrad registry.

    The LabRAD registry can be used like a python class or a list. 
    Registry entries are mapped to valid python identifiers by
    replacing all characters except letters and digits with '_', and by
    prefixing with '_' if the first letter is a digit.
    Python identifiers are mapped to registry entries by removing all '_'
    at the beginning or end and by replacing '_' in the middle with ' '.
    This means that not all registry entries can be accessed as attributes.
    For registry entries that are not valid python names you should use
    attributes e.g. mywrapper['Key Name'].
    
    Examples:

    r = RegistryWrapper(labrad.connect())
    #create a directory
    r['Test'] = {}
    r.Test['Two Words'] = 2
    print r.Test.Two_Words
    r.Test['2 Words']
    print r.Test._2_Words
    r.Test['%$#!'] = 'garbage'
    #won't work
    print r.Test.____

    """
    
    def __init__(self, cxn, directory='', context=None):
        if context == None:
            context = cxn.context()
        object.__setattr__(self,'_ctx', context)    
        object.__setattr__(self,'_cxn', cxn)
        if not isinstance(directory,list):
            directory = [directory]
        if directory[0] != '':
            directory = [''] + directory
        
        object.__setattr__(self,'_dir',directory)
        self._cxn.registry.cd(self._dir, True, context=self._ctx)
        
    def __getitem__(self, name):
        listing = self._cxn.registry.packet(context=self._ctx).\
            cd(self._dir).\
            dir().\
            send().\
            dir
        if name in listing[0]:
            return RegistryWrapper(self._cxn, self._dir + [name], self._ctx)
        elif name in listing[1]:
            return self._cxn.registry.packet(context=self._ctx).\
                cd(self._dir).\
                get(name).\
                send().get
        else:
            raise AttributeError, name
    
    def __setitem__(self, name, value):
        if isinstance(value, dict) or isinstance(value, RegistryWrapper):
            subwrapper = RegistryWrapper(self._cxn, self._dir + [name],
                                         context = self._ctx)
            for element in value:
                subwrapper[element] = value[element]
        else:
            self._cxn.registry.packet(context=self._ctx).\
                cd(self._dir).\
                set(name,value).\
                send()

    def __setattr__(self, name, value):
        self.__setitem__(identifier2str(name), value)

    def __getattr__(self, name):
        return self.__getitem__(identifier2str(name))

    
    def _get_dict(self, asidentifier=True, deep=True):
        listing = self._cxn.registry.packet(context=self._ctx).\
            cd(self._dir).\
            dir().\
            send().dir

        regdict = dictclass()

        for i in listing[0]:
            if asidentifier:
                itemname = str2identifier(i)
            else:
                itemname = i
            subwrapper = RegistryWrapper(self._cxn, self._dir + [i], self._ctx)
            if deep:
                regdict[itemname] = subwrapper._get_dict(asidentifier, True)
            else:
                regdict[itemname] = subwrapper
        for i in listing[1]:
            if asidentifier:
                itemname = str2identifier(i)
            else:
                itemname = i
            regdict[itemname] = self._cxn.registry.packet(context=self._ctx).\
                   cd(self._dir).\
                   get(i).\
                   send().\
                   get
        
        return regdict
    
    __dict__ = property(_get_dict)

    def keys(self):
        return self._get_dict(False, False).keys()
    
    def __iter__(self):
        return self._get_dict(False, False).__iter__()

    def __str__(self):
        return str(self._get_dict(False, True))

    def copy(self, deep=True):
        return self._get_dict(False, deep)

