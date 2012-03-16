# Copyright (C) 2012  Daniel Sank
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
#
# CHANGELOG
#


import labrad
from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.reactor import callLater


"""
### BEGIN NODE INFO
[info]
name = Data Vault
version = 1.0
description = Proxies the data vault so that all LabRAD colonies can use the same data vault
instancename = %LABRADNODE% Data Vault Proxy

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

class DataVaultProxy(LabradServer):
    """Intefaces to data vault"""
    name = 'Data Vault'
        
    @inlineCallbacks
    def initServer(self):
        self.cxnCentral = yield labrad.connectAsync(host='jingle')
        self.dv = self.cxnCentral.data_vault
        
    @setting(5, returns=['*s'])
    def dump_existing_sessions(self, c):
        result = yield self.dv.dump_existing_sessions(context=c)
        returnValue(result)
    
    @setting(6, tagFilters=['s', '*s'], includeTags='b',
                returns=['*s{subdirs}, *s{datasets}',
                         '*(s*s){subdirs}, *(s*s){datasets}'])
    def dir(self, c, tagFilters=['-trash'], includeTags=False):
        """Get subdirectories and datasets in the current directory."""
        result = yield self.dv.dir(tagFilters, includeTags, context=c.ID)
        returnValue(result)
    
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
        result = yield self.dv.cd(path, create, context=c.ID)
        returnValue(result)
            
    @setting(8, name='s', returns='*s')
    def mkdir(self, c, name):
        """Make a new sub-directory in the current directory.
        
        The current directory remains selected.  You must use the
        'cd' command to select the newly-created directory.
        Directory name cannot be empty.  Returns the path to the
        created directory.
        """
        result = yield self.dv.mkdir(name, context=c.ID)
        returnValue(result)
        
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
        result = yield self.dv.new(name, independents, dependents, context=c.ID)
        returnValue(result)
        
    @setting(10, name=['s', 'w'], returns='(*s{path}, s{name})')
    def open(self, c, name):
        """Open a Dataset for reading.
        
        You can specify the dataset by name or number.
        Returns the path and name for this dataset.
        """
        result = yield self.dv.open(name, context=c.ID)
        returnValue(result)
        
    @setting(20, data=['*v: add one row of data',
                       '*2v: add multiple rows of data'],
                 returns='')
    def add(self, c, data):
        """Add data to the current dataset.
        
        The number of elements in each row of data must be equal
        to the total number of variables in the data set
        (independents + dependents).
        """
        result = yield self.dv.add(data, context=c.ID)
        returnValue(result)

    @setting(21, limit='w', startOver='b', returns='*2v')
    def get(self, c, limit=None, startOver=False):
        """Get data from the current dataset.
        
        Limit is the maximum number of rows of data to return, with
        the default being to return the whole dataset.  Setting the
        startOver flag to true will return data starting at the beginning
        of the dataset.  By default, only new data that has not been seen
        in this context is returned.
        """
        result = yield self.dv.get(limit, startover, context=c.ID)
        returnValue(result)
    
    @setting(100, returns='(*(ss){independents}, *(sss){dependents})')
    def variables(self, c):
        """Get the independent and dependent variables for the current dataset.
        
        Each independent variable is a cluster of (label, units).
        Each dependent variable is a cluster of (label, legend, units).
        Label is meant to be an axis label, which may be shared among several
        traces, while legend is unique to each trace.
        """
        result = yield self.dv.variables(context=c.ID)
        returnValue(result)

    @setting(120, returns='*s')
    def parameters(self, c):
        """Get a list of parameter names."""
        result = yield self.dv.parameters(context=c.ID)
        returnValue(result)

    @setting(121, 'add parameter', name='s', returns='')
    def add_parameter(self, c, name, data):
        """Add a new parameter to the current dataset."""
        result = yield self.dv.add_parameter(name, data, context=c.ID)
        returnValue(result)

    @setting(124, 'add parameters', params='?{((s?)(s?)...)}', returns='')
    def add_parameters(self, c, params):
        """Add a new parameter to the current dataset."""
        result = yield self.dv.add_parameters(params, context=c.ID)
        returnValue(result)
        
    @setting(126, 'get name', returns='s')
    def get_name(self, c):
        """Get the name of the current dataset."""
        result = yield self.dv.get_name(context=c.ID)
        returnValue(result)

    @setting(122, 'get parameter', name='s')
    def get_parameter(self, c, name, case_sensitive=True):
        """Get the value of a parameter."""
        result = yield self.dv.get_parameter(name, case_sensitive, context=c.ID)
        returnValue(result)

    @setting(123, 'get parameters')
    def get_parameters(self, c):
        """Get all parameters.
        
        Returns a cluster of (name, value) clusters, one for each parameter.
        If the set has no parameters, nothing is returned (since empty clusters
        are not allowed).
        """
        result = yield self.dv.get_parameters(context=c.ID)
        returnValue(result)

    @setting(125, 'import parameters',
                  subdirs=[' : Import current directory',
                           'w: Include this many levels of subdirectories (0=all)',
                           '*s: Include these subdirectories'],
                  returns='')
    def import_parameters(self, c, subdirs=None):
        """Reads all entries from the current registry directory, optionally
        including subdirectories, as parameters into the current dataset."""
        result = yield self.dv.import_parameters(subdirs, context=c.ID)
        returnValue(result)
        

    @setting(200, 'add comment', comment=['s'], user=['s'], returns=[''])
    def add_comment(self, c, comment, user='anonymous'):
        """Add a comment to the current dataset."""
        result = yield self.dv.add_comment(comment, user, context=c.ID)
        returnValue(result)
        
    @setting(201, 'get comments', limit=['w'], startOver=['b'],
                                  returns=['*(t, s{user}, s{comment})'])
    def get_comments(self, c, limit=None, startOver=False):
        """Get comments for the current dataset."""
        result = yield self.dv.get_comments(limit, startOver, context=c.ID)
        returnValue(result)

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
        result = yield self.dv.update_tags(tags, dirs, datasets, context=c.ID)
        returnValue(result)

    @setting(301, 'get tags',
                  dirs=['s', '*s'], datasets=['s', '*s'],
                  returns='*(s*s)*(s*s)')
    def get_tags(self, c, dirs, datasets):
        """Get tags for directories and datasets in the current dir."""
        result = yield self.dv.get_tags(dirs, datasets, context=c.ID)
        returnValue(result)
        
        
__server__ = DataVaultProxy()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
