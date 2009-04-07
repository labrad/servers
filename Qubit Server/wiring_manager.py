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
from labrad.server import LabradServer, setting

from twisted.internet.defer import inlineCallbacks, returnValue

from datetime import datetime

from copy import deepcopy

import struct

import numpy
from scipy.signal import slepian

SRAMPREPAD  = 20
SRAMPOSTPAD = 80

SRAMPAD = SRAMPREPAD + SRAMPOSTPAD

class QubitServer(LabradServer):
    """This server abstracts the implementation details of the GHz DACs' functionality as well as the physical wiring to the fridge"""
    name = 'Qubits'

    def curQubit(self, ctxt):
        if 'Qubit' not in ctxt:
            raise NoQubitSelectedError()
        if ctxt['Qubit'] not in self.Qubits:
            raise NoQubitSelectedError()
        return self.Qubits[ctxt['Qubit']]

    def getQubit(self, name):
        if name not in self.Qubits:
            raise QubitNotFoundError(name)
        return self.Qubits[name]

    def getExperiment(self, c):
        if 'Experiment' not in c:
            raise NoExperimentError()
        return c['Experiment']
        
    @inlineCallbacks
    def saveVariable(self, folder, name, variable):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Qubit Server', folder], True)
        p.set(name, repr(variable))
        ans = yield p.send()
        returnValue(ans.set)

    @inlineCallbacks
    def loadVariable(self, folder, name):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Qubit Server', folder], True)
        p.get(name)
        ans = yield p.send()
        data = T.evalLRData(ans.get)
        returnValue(data)

    @inlineCallbacks
    def listVariables(self, folder):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Qubit Server', folder], True)
        p.dir()
        ans = yield p.send()
        returnValue(ans.dir[1])

    @inlineCallbacks
    def initServer(self):
        self.Qubits = {}
        self.Setups = {}
        cxn = self.client
        self.GHzDACs = yield cxn.ghz_dacs.list_devices()
        self.GHzDACs = [d for i, d in self.GHzDACs]
        self.Anritsus = yield cxn.anritsu_server.list_devices()
        self.Anritsus = [d for i, d in self.Anritsus]
        self.DACchannels  = ['DAC A', 'DAC B']
        self.FOchannels   = [ 'FO 0',  'FO 1']
        self.FOcommands   = [0x100000, 0x200000]
        self.Trigchannels = ['S 0', 'S 1', 'S 2', 'S 3']
        # autoload all qubits and setups
        qubits = yield self.list_saved_qubits(None)
        for qubit in qubits:
            print 'loading qubit "%s"...' % qubit
            yield self.load_qubit(None, qubit)
        setups = yield self.list_saved_setups(None)
        for setup in setups:
            print 'loading setup "%s"...' % setup
            yield self.load_setup(None, setup)


    @setting(1, "Connect Fiber", dac='ss', card='ss')
    def connect_fiber(self, c, dac, card):
        pass

    @setting(2, "Disconnect Fiber", dac='ss', card='ss')
    def disconnect_fiber(self, c, dac, card):
        pass
        
__server__ = QubitServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
