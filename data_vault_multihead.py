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
name = Data Vault
version = 2.3.7-hydra
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

import sys
import os
import re
import warnings

from twisted.application.service import MultiService
from twisted.application.internet import TCPClient
from twisted.internet import reactor
from twisted.internet.reactor import callLater
from twisted.internet.defer import inlineCallbacks, returnValue, maybeDeferred
import twisted.internet.task

import labrad
from labrad import constants, types as T, util
from labrad.server import LabradServer, Signal, setting
import labrad.wrappers

import datavault as dv
from datavault import errors

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


# TODO: tagging
# - search globally (or in some subtree of sessions) for matching tags
#     - this is the least common case, and will be an expensive operation
#     - don't worry too much about optimizing this
#     - since we won't bother optimizing the global search case, we can store
#       tag information in the session


# One instance per manager.  Not persistent, recreated when connection is lost/regained
class DataVault(LabradServer):
    name = 'Data Vault'

    def __init__(self, host, port, password, hub, path, session_store):
        LabradServer.__init__(self)
        self.host = host
        self.port = port
        self.password = password
        self.hub = hub
        self.path = path
        self.session_store = session_store
        self.alive = False

        # session signals
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
        self.alive = True
        _root = self.session_store.get([''])
        self.keepalive_timer = twisted.internet.task.LoopingCall(self.keepalive)
        self.onShutdown().addBoth(self.end_keepalive)
        self.keepalive_timer.start(120)

    def end_keepalive(self, *ignored):
        # stopServer is only called when the whole application shuts down.
        # We need to manually use the onShutdown() callback
        self.keepalive_timer.stop()

    @inlineCallbacks
    def keepalive(self):
        print "sending keepalive to %s:%d" % (self.host, self.port)
        p = self.client.manager.packet()
        p.echo('123')
        try:
            yield p.send()
        except:
            pass # We don't care about errors, dropped connections will be recognized automatically

    def initContext(self, c):
        # start in the root session
        c['path'] = ['']
        # start listening to the root session
        c['session'] = self.session_store.get([''])
        c['session'].listeners.add(ExtendedContext(self, c.ID))
        #print "Adding %s to listeners for %s" % (c.ID, [''])

    def expireContext(self, c):
        """Stop sending any signals to this context."""
        ctx = ExtendedContext(self, c.ID)
        def removeFromList(ls):
            if ctx in ls:
                ls.remove(ctx)
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

    @setting(7, target = ['       : {get current directory}',
                          's      : {change into this directory}',
                          '*s     : {change into each directory in sequence}',
                          'w      : {go up by this many directories}',
                          '(s, b) : Enter subdirectory "s", creating it as needed if "b"==True', 
                          '(*s, b): Enter subdirectories "*s", creating it as needed if "b"==True'], 
                returns='*s')
    def cd(self, c, target=None):
        """Change the current directory.

        The empty string '' refers to the root directory. If the 'create' flag
        is set to true, new directories will be created as needed.
        Returns the path to the new current directory.
        """
        if target is None:
            return c['path']
        if isinstance(target, tuple):
            path, create = target
        else:
            path = target
            create = False

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
                session = self.session_store.get(temp) # touch the session
        if c['path'] != temp:
            # stop listening to old session and start listening to new session
            ctx = ExtendedContext(self, c.ID)
            #print "removing %s from session %s" % (ctx, c['path'])
            c['session'].listeners.remove(ctx)
            session = self.session_store.get(temp)
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
        ctx = ExtendedContext(self, c.ID)
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
            running = hasattr(s, 'server') and bool(s.server.alive)
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
        dvc = DataVaultConnector(host, port, password, self.hub, self.path, self.session_store)
        dvc.setServiceParent(self.hub)
        #self.hub.addService(DataVaultConnector(host, port, password, self.hub, self.path))

    @setting(403, 'Ping Managers')
    def ping_managers(self, c):
        self.hub.ping()

    @setting(404, 'Kick Managers', host_regex='s', port='w')
    def kick_managers(self, c, host_regex, port=0):
        self.hub.kick(host_regex, port)

    @setting(405, 'Reconnect', host_regex='s', port='w')
    def reconnect(self, c, host_regex, port=0):
        self.hub.reconnect(host_regex, port)

    @setting(406, 'Refresh Managers')
    def refresh_managers(self, c):
        return self.hub.refresh_managers()


# One instance per manager, persistant (not recreated when connections are dropped)
class DataVaultConnector(MultiService):
    """Service that connects the Data Vault to a single LabRAD manager

    If the manager is stopped or we lose the network connection,
    this service attempts to reconnect so that we will come
    back online when the manager is back up.
    """
    reconnectDelay = 10

    def __init__(self, host, port, password, hub, path, session_store):
        MultiService.__init__(self)
        self.host = host
        self.port = port
        self.password = password
        self.hub = hub
        self.path = path
        self.session_store = session_store
        self.die = False

    def startService(self):
        MultiService.startService(self)
        self.startConnection()

    def startConnection(self):
        """Attempt to start the data vault and connect to LabRAD."""
        print 'Connecting to %s:%d...' % (self.host, self.port)
        self.server = DataVault(self.host, self.port, self.password, self.hub, self.path, self.session_store)
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
        if self.die:
            print "Connecting terminating permanently"
            self.stopService()
            self.disownServiceParent()
            return False
        else:
            reactor.callLater(self.reconnectDelay, self.startConnection)
            print 'Will try to reconnect to %s:%d in %d seconds...' % (self.host, self.port, self.reconnectDelay)

# Hub object: one instance total
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
        self.session_store = dv.SessionStore(path, self)
        for signal in self.signals:
            self.wrapSignal(signal)
        for host, port, password in managers:
            x = DataVaultConnector(host, port, password, self, self.path, self.session_store)
            x.setServiceParent(self)
            #self.addService(DataVaultConnector(host, port, password, self, self.path))

    def connect(self, server):
        print 'server connected: %s:%d' % (server.host, server.port)
        self.servers.add(server)

    def disconnect(self, server):
        print 'server disconnected: %s:%d' % (server.host, server.port)
        if server in self.servers:
            self.servers.remove(server)

    def reconnect(self, host_regex, port=0):
        '''
        Drop the connection to the specified host(s).  They will auto-reconnect.
        '''
        for s in self.servers:
            if re.match(host_regex, s.host) and (port == 0 or s.port==port):
                s._cxn.disconnect()

    def ping(self):
        '''
        Ping all attached managers as a keepalive/dropped connection detection mechanism
        '''
        for s in self.servers:
            s.keepalive()
            #s.client.manager.packet()
            #p.echo('123')
            #result = yield p.send()
            # x = result.echo
        # return result

    def kick(self, host_regexp, port=0):
        '''
        Disconnect from a manager and don't reconnect.
        '''
        for connector in self:
            if re.match(host_regexp, connector.host) and (port == 0 or port == connector.port):
                connector.die = True
                try:
                    connector.server._cxn.disconnect()
                except Exception:
                    pass

    @inlineCallbacks
    def refresh_managers(self):
        '''
        Refresh list of managers from the registry.  New servers will be added.  Existing servers
        will *not* be removed, even if they are no longer in the registry.  Use "kick" to disconnect
        them.
        '''

        # We don't know which (if any) managers are live.  For now, just make a new client connection
        # to the "primary" manager.

        cxn = yield labrad.wrappers.connectAsync()
        path = ['', 'Servers', 'Data Vault', 'Multihead']
        reg = cxn.registry
        p = reg.packet()
        p.cd(path)
        p.get("Managers", "*(sws)", key="managers")
        ans = yield p.send()
        for (host, port, password) in ans.managers:
            if not port:
                port = constants.MANAGER_PORT
            if not password:
                password = constants.PASSWORD
            for connector in self:
                if connector.host == host and connector.port == port:
                    break
            else:
                dvc = DataVaultConnector(host, port, password, self, self.path, self.session_store)
                dvc.setServiceParent(self)
                #self.addService(DataVaultConnector(host, port, password, self, self.path))

        cxn.disconnect()
        return

    def __str__(self):
        managers = ['%s:%d' % (connector.host, connector.port) for connector in self]
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

@inlineCallbacks
def load_settings_registry(cxn):
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
    path = ['', 'Servers', 'Data Vault', 'Multihead']
    reg = cxn.registry
    # try to load for this node
    p = reg.packet()
    p.cd(path)
    p.get("Repository", 's', key="repo")
    p.get("Managers", "*(sws)", key="managers")
    p.get("Node", "s", False, "", key="node")
    ans = yield p.send()
    if ans.node and (ans.node != util.getNodeName()):
        raise RuntimeError('Node name "%s" from registry does not match current host "%s"' % (ans.node, util.getNodeName()))
    cxn.disconnect()
    returnValue((ans.repo, ans.managers))

def load_settings_cmdline(argv):
    if len(argv) < 3:
        raise RuntimeError('Incorrect command line')
    path = argv[1]
    # We lock the datavault path, but we can't check the node lock unless using
    # --auto to get the data from the registry.
    manager_list = argv[2:]
    managers = []
    for m in manager_list:
        password, sep, hostport = m.rpartition('@')
        host, sep, port = hostport.partition(':')
        if sep == '':
            port = 0
        else:
            port = int(port)
        managers.append((host, port, password))
    return path, managers

def start_server(args):
    path, managers = args
    if not os.path.exists(path):
        raise Exception('data path %s does not exist' % path)
    if not os.path.isdir(path):
        raise Exception('data path %s is not a directory' % path)

    def parseManagerInfo(manager):
        host, port, password = manager
        if not password:
            password = constants.PASSWORD
        if not port:
            port = constants.MANAGER_PORT
        return (host, port, password)

    lock_path(path)
    managers = [parseManagerInfo(m) for m in managers]
    service = DataVaultServiceHost(path, managers)
    service.startService()

def main(argv=sys.argv):
    @inlineCallbacks
    def start():
        try:
            if len(argv) > 1 and argv[1] == '--auto':
                cxn = yield labrad.wrappers.connectAsync()
                settings = yield load_settings_registry(cxn)
            else:
                settings = load_settings_cmdline(argv)
            start_server(settings)
        except Exception as e:
            print e
            print 'usage: %s /path/to/vault/directory [password@]host[:port] [password2]@host2[:port2] ...' % (argv[0])
            reactor.callWhenRunning(reactor.stop)

    _ = start()
    reactor.run()

if __name__ == '__main__':
    main()
