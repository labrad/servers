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

"""
### BEGIN NODE INFO
[info]
name = Data Vault
version = 2.3.4
description = Store and retrieve numeric data

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

# CHANGELOG
#
# 31 January 2012 - Dan Sank and Ted White
# Added setting to dump existing open sessions in Session._sessions.
# We did this because the data vault seems to be leaking memory.
# We think sessions are never getting garbage collected
# even after all listening contexts expire. We want to be able to view all
# existing sessions to see if this is causing the memory leak.

from __future__ import with_statement

import os
import sys

from twisted.internet.defer import inlineCallbacks

from labrad.server import LabradServer, Signal, setting
import labrad.util

import datavault as dv
from datavault import errors


# TODO: tagging
# - search globally (or in some subtree of sessions) for matching tags
#     - this is the least common case, and will be an expensive operation
#     - don't worry too much about optimizing this
#     - since we won't bother optimizing the global search case, we can store
#       tag information in the session


class DataVault(LabradServer):
    name = 'Data Vault'

    @inlineCallbacks
    def initServer(self):
        # load configuration info from registry
        try:
            path = ['', 'Servers', self.name, 'Repository']
            nodename = labrad.util.getNodeName()
            reg = self.client.registry
            try:
                # try to load for this node
                p = reg.packet()
                p.cd(path)
                p.get(nodename, 's')
                ans = yield p.send()
            except:
                # try to load default
                p = reg.packet()
                p.cd(path)
                p.get('__default__', 's')
                ans = yield p.send()
            datadir = ans.get
        except:
            try:
                print 'Could not load repository location from registry.'
                print 'Please enter data storage directory or hit enter to use the current directory:'
                datadir = raw_input('>>>')
                if datadir == '':
                    datadir = os.path.join(os.path.split(__file__)[0], '__data__')
                if not os.path.exists(datadir):
                    os.makedirs(datadir)
                # set as default and for this node
                p = reg.packet()
                p.cd(path, True)
                p.set(nodename, datadir)
                p.set('__default__', datadir)
                yield p.send()
                print datadir, "has been saved in the registry",
                print "as the data location."
                print "To change this, stop this server,"
                print "edit the registry keys at", path,
                print "and then restart."
            except Exception, E:
                print
                print E
                print
                print "Press [Enter] to continue..."
                raw_input()
                sys.exit()
        self.session_store = dv.SessionStore(datadir, self)
        # create root session
        _root = self.session_store.get([''])

    def initContext(self, c):
        # start in the root session
        c['path'] = ['']
        # start listening to the root session
        c['session'] = self.session_store.get([''])
        c['session'].listeners.add(c.ID)

    def expireContext(self, c):
        """Stop sending any signals to this context."""
        def removeFromList(ls):
            if c.ID in ls:
                ls.remove(c.ID)
        for session in self.session_store.get_all():
            removeFromList(session.listeners)
            for dataset in session.datasets.values():
                removeFromList(dataset.listeners)
                removeFromList(dataset.param_listeners)
                removeFromList(dataset.comment_listeners)

    def getSession(self, c):
        """Get a session object for the current path."""
        return c['session']

    def getDataset(self, c):
        """Get a dataset object for the current dataset."""
        if 'dataset' not in c:
            raise errors.NoDatasetError()
        return c['datasetObj']

    # session signals
    onNewDir = Signal(543617, 'signal: new dir', 's')
    onNewDataset = Signal(543618, 'signal: new dataset', 's')
    onTagsUpdated = Signal(543622, 'signal: tags updated', '*(s*s)*(s*s)')

    # dataset signals
    onDataAvailable = Signal(543619, 'signal: data available', '')
    onNewParameter = Signal(543620, 'signal: new parameter', '')
    onCommentsAvailable = Signal(543621, 'signal: comments available', '')


    @setting(5, returns=['*s'])
    def dump_existing_sessions(self, c):
        sessions = []
        for session in self.session_store.geta_all():
            sessionString=''
            for s in session.path:
                sessionString += s+'/'
            sessions.append(sessionString)
        return sessions

    @setting(6, tagFilters=['s', '*s'], includeTags='b',
                returns=['*s{subdirs}, *s{datasets}',
                         '*(s*s){subdirs}, *(s*s){datasets}'])
    def dir(self, c, tagFilters=['-trash'], includeTags=False):
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

        temp = c['path'][:] # copy the current path
        if isinstance(path, (int, long)):
            if path > 0:
                temp = temp[:-path]
                if not len(temp):
                    temp = ['']
        else:
            if isinstance(path, str):
                path = [path]
            for segment in path:
                if segment == '':
                    temp = ['']
                else:
                    temp.append(segment)
                if not self.session_store.exists(temp) and not create:
                    raise errors.DirectoryNotFoundError(temp)
                _session = self.session_store.get(temp) # touch the session
        if c['path'] != temp:
            # stop listening to old session and start listening to new session
            c['session'].listeners.remove(c.ID)
            session = self.session_store.get(temp)
            session.listeners.add(c.ID)
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
            raise errors.EmptyNameError()
        path = c['path'] + [name]
        if self.session_store.exists(path):
            raise errors.DirectoryExistsError(path)
        _sess = self.session_store.get(path) # make the new directory
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
        dataset.keepStreaming(c.ID, 0)
        dataset.keepStreamingComments(c.ID, 0)
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
        #Check for unfavored persons, and make them wait
        # if 'Matteo' in dataset.session:
            # start = time.time()
            # while time.time()-start<3:
                # yield
        if not c['writing']:
            raise errors.ReadOnlyError()
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
        dataset.keepStreaming(c.ID, c['filepos'])
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
        dataset.param_listeners.add(c.ID) # send a message when new parameters are added
        return [par['label'] for par in dataset.parameters]

    @setting(121, 'add parameter', name='s', returns='')
    def add_parameter(self, c, name, data):
        """Add a new parameter to the current dataset."""
        dataset = self.getDataset(c)
        dataset.addParameter(name, data)

    @setting(124, 'add parameters', params='?{((s?)(s?)...)}', returns='')
    def add_parameters(self, c, params):
        """Add a new parameter to the current dataset."""
        dataset = self.getDataset(c)
        dataset.addParameters(params)


    @setting(126, 'get name', returns='s')
    def get_name(self, c):
        """Get the name of the current dataset."""
        dataset = self.getDataset(c)
        name = dataset.name
        return name

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
        dataset.param_listeners.add(c.ID) # send a message when new parameters are added
        if len(params):
            return params


    @inlineCallbacks
    def read_pars_int(self, c, ctx, dataset, curdirs, subdirs=None):
        p = self.client.registry.packet(context=ctx)
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
                  subdirs=[' : Import current directory',
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


    @setting(200, 'add comment', comment=['s'], user=['s'], returns=[''])
    def add_comment(self, c, comment, user='anonymous'):
        """Add a comment to the current dataset."""
        dataset = self.getDataset(c)
        return dataset.addComment(user, comment)

    @setting(201, 'get comments', limit=['w'], startOver=['b'],
                                  returns=['*(t, s{user}, s{comment})'])
    def get_comments(self, c, limit=None, startOver=False):
        """Get comments for the current dataset."""
        dataset = self.getDataset(c)
        c['commentpos'] = 0 if startOver else c['commentpos']
        comments, c['commentpos'] = dataset.getComments(limit, c['commentpos'])
        dataset.keepStreamingComments(c.ID, c['commentpos'])
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


__server__ = DataVault()

if __name__ == '__main__':
    labrad.util.runServer(__server__)
