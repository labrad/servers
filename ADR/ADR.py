# Copyright (C) 2010  Daniel Sank
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
name = ADR
version = 0.1
description = Controls an ADR setup

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.devices import DeviceServer, DeviceWrapper
from labrad import types as T, util
from labrad.server import setting
from twisted.internet.defer import inlineCallbacks, returnValue

import numpy as np

#Registry path to ADR configurations
CONFIG_PATH = ['','Servers','ADR']

class ADRWrapper(DeviceWrapper):

##    def __init__(self, guid, name):
##        #Add stuff here#
##        self.__init__(self, guid, names)

    @inlineCallbacks
    def connect(self, *args, **peripheralDict):
        """     
        TODO: Add error checking and handling
        """
        #Give the ADR a client connection to LabRAD.
        #ADR's use the same connection as the ADR server.
        #Each ADR makes LabRAD requests in its own context.
        self.cxn = args[0]
        self.ctxt = self.cxn.context()
        yield self.refreshPeripherals()

    @inlineCallbacks
    def refreshPeripherals(self):
        self.allPeripherals = yield self.findPeripherals()
        self.peripheralOrphans = {}
        self.peripheralsConnected = {}
        for peripheralName, idTuple in self.allPeripherals.items():
            yield self.attemptPeripheral((peripheralName, idTuple))

    @inlineCallbacks
    def findPeripherals(self):
        """Finds peripheral device definitions for a given ADR
        OUTPUT
            peripheralDict - dictionary {peripheralName:(serverName,identifier)..}
        """
        reg = self.cxn.registry
        yield reg.cd(CONFIG_PATH + [self.name])
        dirs, keys = yield reg.dir()
        p = reg.packet()
        for peripheral in keys:
            p.get(peripheral, key=peripheral)
        ans = yield p.send()
        peripheralDict = {}
        for peripheral in keys: #all key names in this directory
            peripheralDict[peripheral] = ans[peripheral]
        returnValue(peripheralDict)

    def attemptOrphans(self):
        for peripheralName, idTuple in self.peripheralOrphans.items():
            self.attemptPeripheral((peripheralName, idTuple))

    @inlineCallbacks
    def attemptPeripheral(self,peripheralTuple):
        """
        Attempts to connect to a specified peripheral. If the peripheral's server exists and
        the desired peripheral is known to that server, then the peripheral is selected in
        this ADR's context. Otherwise the peripheral is added to the list of orphans.
        
        INPUTS:
        peripheralTuple - (peripheralName,(serverName,peripheralIdentifier))
        """
        peripheralName = peripheralTuple[0]
        serverName = peripheralTuple[1][0]
        peripheralID = peripheralTuple[1][1]

        #If the peripheral's server exists, get it,
        if serverName in self.cxn.servers:
            server = self.cxn.servers[serverName]
        #otherwise orphan this peripheral and tell the user.
        else:
            self._orphanPeripheral(peripheralTuple)
            print 'Server ' + serverName + ' does not exist.'
            print 'Check that the server is running and refresh this ADR'
            return

        # If the peripheral's server has this peripheral, select it in this ADR's context.
        devices = yield server.list_devices()
        if peripheralID in [device[1] for device in devices]:
            yield self._connectPeripheral(server, peripheralTuple)
        # otherwise, orphan it
        else:
            print 'Server '+ serverName + ' does not have device ' + peripheralID
            self._orphanPeripheral(peripheralTuple)

    @inlineCallbacks
    def _connectPeripheral(self, server, peripheralTuple):
        peripheralName = peripheralTuple[0]
        idTuple = peripheralTuple[1]
        #Make the actual connection to the peripheral device!
        yield server.select_device(idTuple[1], context=self.ctxt)
        if peripheralName not in self.peripheralsConnected:
            self.peripheralsConnected[peripheralName] = idTuple

    def _orphanPeripheral(self,peripheralTuple):
        peripheralName = peripheralTuple[0]
        idTuple = peripheralTuple[1]
        if peripheralName not in self.peripheralOrphans:
            self.peripheralOrphans[peripheralName] = idTuple

class ADRServer(DeviceServer):
    name = 'ADR Server'
    deviceName = 'ADR'
    deviceWrapper = ADRWrapper
    
    def initServer(self):
        return DeviceServer.initServer(self)
    
    def stopServer(self):
        return DeviceServer.stopServer(self)

    @inlineCallbacks
    def findDevices(self):
        """Finds all ADR configurations in the registry at CONFIG_PATH and returns a list of (ADR_name,(),peripheralDictionary).
        INPUTS - none
        OUTPUT - List of (ADRName,(connectionObject,context),peripheralDict) tuples.
        """
        deviceList=[]
        reg = self.client.registry
        yield reg.cd(CONFIG_PATH)
        resp = yield reg.dir()
        ADRNames = resp[0].aslist
        for name in ADRNames:
            deviceList.append((name,(self.client,)))
        returnValue(deviceList)

    #################
    #TED, START HERE#
    #################

__server__ = ADRServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
