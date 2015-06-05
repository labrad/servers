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
class DataVaultMultiHead(DataVault):
    name = 'Data Vault'

    def __init__(self, host, port, password, hub, path, session_store):
        DataVault.__init__(self, session_store)
        self.host = host
        self.port = port
        self.password = password
        self.hub = hub
        self.path = path
        self.alive = False

    def initServer(self):
        DataVault.initServer(self)
        # let the DataVaultHost know that we connected
        self.hub.connect(self)
        self.alive = True
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

    def listenerKey(self, c):
        return ExtendedContext(self, c.ID)

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
