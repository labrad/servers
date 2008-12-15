# Copyright (C) 2008  Matthew Neeley
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
name = Logger
version = 1.0
description = Manages log files with the data vault and registry.

[startup]
cmdline = %PYTHON% log_server.py
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad.server import LabradServer, setting, inlineCallbacks, returnValue
from labrad.units import degC, K, psi, torr, min as minutes, A

from datetime import datetime

# registry (metadata about logs and nonnumeric logs)
# Logs -> {logPath} -> {YYYY} -> {MM} -> {DD}

# data vault (for logging of numerical data)
# Logs -> {logPath} -> {YYYY} -> {MM} -> {DD}

class Log(object):
    def __new__(self):
        pass

    def __getitem__(self, key):
        """Get or create a variable with the specified key."""

class Channel(object):
    def __new__(self):
        pass
    
    def __init__(self):
        pass

    def addEntry(self, time, value):
        """Add an entry for this channel."""

class Logger(LabradServer):
    name = 'Logger'

    @inlineCallbacks
    def initServer(self):
        pass

    onNewLog = Signal(654321, 'signal: new log', '*s')
    onNewVar = Signal(654322, 'signal: new channel', 'ss')
    onNewData = Signal(654323, 'signal: new data', '')

    def getLog(self, c):
        if 'log' not in c:
            raise Exception('No log opened in this context.')
        return c['log']

    @setting(1, 'list', filters=['s', '*s'])
    def get_log_list(self, c, filters):
        """Get a list of available logs matching the given filters.
        """

    @setting(2, 'describe', logPath=['s', '*s'],
             returns='t{start} t{last} *(s{name} s{type} t{start} t{last})
    def describe(self, c, logPath):
        """Get information about the specified log.
        """
    
    @setting(100, 'open', logPath=['s', '*s'], create='b',
             returns='t{start} t{last} *(s{name} s{type} t{start} t{last})')
    def open_log(self, c, logPath, create=False):
        """Open a new log file path.

        If this log file path does not exist and create is True,
        it will be created, otherwise an error will be thrown.

        Returns the start time of the log, as well as a list
        with the name and type tag of each channel in the log.
        """

    @setting(300, 'log', data='?: ((s?)(s?)...)', returns='')
    def log_data(self, c, data):
        """Add a Log entry to the current log file.

        The data to be logged should be sent as a cluster
        of two-element clusters, each with a channel name
        and a value.  If a channel has not been used before
        in the current log, it will be added to the log file
        and the datatype of the value for this channel will be
        recorded.  Thereafter, data logged on this channel
        name must have the same type.
        """
        log = self.getLog(c)
        t = datetime.now()
        for key, value in data:
            log[key].addEntry(t, value)

    @setting(400, 'get',
             channels=['s', '*s'], range=['t', 'tt'], limit='w',
             returns='?: (*(t?)*(t?)...)')
    def get_data(self, c, channels, range, limit=1000):
        """Get log entries in the specified range of time.

        Returns a cluster of lists of values, one list for each channel
        requested.  Note that a cluster is returned even if only one
        channel is requested

        The time range can be specified with a beginning and end, in
        which case a finite range will be sent, or as a beginning only,
        in which case this get will remain open, and the client can be
        notified when new data is added in the future.  To be notified
        of new messages, sign up for the 'new data' signal.

        Limit specifies the maximum number of entries to allow in any
        given list.  If there is more data available beyond the limit,
        a 'new data' message will be fired to listeners signed up for
        the message.  This is the same 'streaming' protocol used by
        clients of the data vault.
        """
        
#####
# Create a server instance and run it

__server__ = Logger()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)


