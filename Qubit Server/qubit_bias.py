# Copyright (C) 2008  Markus Ansmann
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
## BEGIN NODE INFO
[info]
name = Qubit Bias
version = 2.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
## END NODE INFO
"""

from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import us, mV

from twisted.python         import log
from twisted.internet       import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

# parameters needed for the reset/initialization sequence for each qubit
INIT_PARAMETERS = [('Reset Bias Low',          'v[mV]', -1000.0*mV),
                   ('Reset Bias High',         'v[mV]', -1000.0*mV),
                   ('Reset Settling Time',     'v[us]',     4.3*us),
                   ('Reset Cycles',            'w',         0L    ),
                   ('Reset Delay',             'v[us]',     0.0*us),
                   ('Idle Bias',               'v[mV]',     0.0*mV),
                   ('Operating Bias',          'v[mV]',    50.0*mV),
                   ('Operating Settling Time', 'v[us]',    40.0*us),
                   ('Squid Zero Bias',         'v[mV]',    40.0*us)]

# parameters needed for the readout sequence for each qubit
READ_PARAMETERS = [('Readout Bias',            'v[mV]',  -500.0*mV),
                   ('Readout Settling Time',   'v[us]',    10.0*us),
                   ('Squid Ramp Delay',        'v[us]',     0.0*us),
                   ('Squid Ramp Start',        'v[mV]',   500.0*mV),
                   ('Squid Ramp End',          'v[mV]',  1500.0*mV),
                   ('Squid Ramp Time',         'v[us]',    15.0*us),
                   ('Squid Zero Bias',         'v[mV]',     0.0*mV),
                   ('Idle Time',               'v[us]',     4.3*us),
                   ('|1>-State Cutoff',        'v[us]',    10.0*us)]

MIN_DELAY = 4.3 # minimum delay after sending bias commands, in us

# commands for FastBias boards
def DAC0(V):
    V = int(V*65535.0/2500.0) & 0xFFFF
    return 0x100000 + (V << 3)

def DAC0noselect(V):
    V = int((V+2500.0)*65535.0/5000.0) & 0xFFFF
    return 0x180004 + (V << 3)

def DAC1fast(V):
    V = int((V+2500.0)*65535.0/5000.0) & 0xFFFF
    return 0x180000 + (V << 3)

def DAC1slow(V):
    V = int((V+2500.0)*65535.0/5000.0) & 0xFFFF
    return 0x180004 + (V << 3)

def maxDelay(delays):
    return max(MIN_DELAY, max(delays))

class QubitBiasServer(LabradServer):
    """Creates basic sequences for controlling qubit bias.

    These are standard sequences for any qubit experiment, such as
    resetting and reading out by ramping the measurement squid.
    """
    name = 'Qubit Bias'
    sendTracebacks = False
                  
    def getQubits(self, c):
        """Get a list of qubits used in the current experiment."""
        return self.client.qubits.experiment_involved_devices('qubit', context=c.ID)

    @inlineCallbacks
    def readParameters(self, c, qubits, parameters):
        """Read parameters from the registry for each qubit.
        
        Any parameters that do not yet exist will be created
        and set to the default values specified above.
        """
        p = self.client.registry.packet() # start a new packet
        p.duplicate_context(c.ID) # copy client directory and overrides
        for n in qubits:
            p.cd([n, 'bias'], True) # change into qubit directory
            for name, typ, default in parameters: # load parameters
                p.get(name, typ, True, default, key=(n, name))
            p.cd(2) # change back to root directory
        ans = yield p.send()
        # build and return parameter dictionary
        pars = {}
        for n in qubits:
            pars[n] = {}
            for name, typ, default in parameters:
                pars[n][name] = float(ans[n, name])
        returnValue(pars)


    @setting(100, 'Initialize Qubits', returns='*v[mV]: Operating Biases')
    def initialize(self, c):
        """Send qubit initialization commands to Qubit Server.
        
        Returns a list of operating biases for
        each qubit in the current experiment.
        """
        qubits = yield self.getQubits(c)
        pars = yield self.readParameters(c, qubits, INIT_PARAMETERS)

        # create a packet for the qubit server
        p = self.client.qubits.packet(context=c.ID)

        # go to idle bias on all Squid and Flux lines
        initFluxReset = [((n, 'Flux'), DAC1fast(pars[n]['Idle Bias'])) for n in qubits]
        initSquidReset = [((n, 'Squid'), DAC1fast(pars[n]['Squid Zero Bias'])) for n in qubits]
        p.memory_bias_commands(initFluxReset + initSquidReset, MIN_DELAY*us)

        # build TODO List based on requested Reset Delays
        todo = {}
        for n in qubits:
            delay = pars[n]['Reset Delay']
            if delay not in todo:
                todo[delay] = []
            todo[delay].append(n)

        curDelay = 0.0
        for delay in sorted(todo.keys()):
            # add any necessary delays (initial delays get stripped)
            if (curDelay > 0) and (delay > curDelay):
                p.memory_delay(delay - curDelay)
            curDelay = delay

            # build reset sequences, all with the same length and number of cycles
            now = todo[delay]
            reset1 = [((n, 'Flux'), DAC1fast(pars[n]['Reset Bias High'])) for n in now]
            reset2 = [((n, 'Flux'), DAC1fast(pars[n]['Reset Bias Low'])) for n in now]
            maxResetSettling = maxDelay(pars[n]['Reset Settling Time'] for n in now)
            maxCount = max(pars[n]['Reset Cycles'] for n in now)
            
            # add commands to packet
            p.memory_bias_commands(reset2, maxResetSettling*us)
            for a in range(int(maxCount)):
                p.memory_bias_commands(reset1, maxResetSettling*us)
                p.memory_bias_commands(reset2, maxResetSettling*us)
            p.memory_bias_commands(initreset, MIN_DELAY*us)

            # update delay for the next set of resets
            curDelay += maxResetSettling*(1 + 2*int(maxCount)) + MIN_DELAY

        # go to operating bias on all Qubits
        setOp = [((n, 'Flux'), DAC1fast(qpars['Operating Bias'])) for n in qubits]
        maxBiasSettling = max(MIN_DELAY, max(pars[n]['Operating Settling Time'] for n in qubits))
        p.memory_bias_commands(setOp, maxBiasSettling*us)
        
        # send sequence to the qubit server
        yield p.send()

        returnValue([pars[n]['Operating Bias'] for n in qubits])


    @setting(101, 'Readout Qubits', returns='*v[us]: |1>-State Cutoffs')
    def readout(self, c):
        """Send qubit readout commands to Qubit Server.
        
        Returns a list of cutoff times for each qubit in
        the current experiment.  Note that a negative cutoff
        means that the |1> state switches BEFORE the |0> state.
        """
        qubits = yield self.getQubits(c)
        pars = yield self.readParameters(c, qubits, READ_PARAMETERS)
        
        # start packet to qubit server
        p = self.client.qubits.packet(context=c.ID)

        # go to readout bias and wait for max settling time
        setReadout = [((n, 'Flux'), DAC1fast(pars[n]['Readout Bias'])) for n in qubits]
        maxSettling = max(MIN_DELAY, max(pars[n]['Readout Settling Time'] for n in qubits))
        p.memory_bias_commands(setReadout, maxSettling*us)
        
        # Build TODO List based on requested Squid Ramp Delays
        todo = {}
        for n in qubits:
            delay = pars[n]['Squid Ramp Delay']
            if delay not in todo:
                todo[delay] = []
            todo[delay].append(n)

        curDelay = 0.0
        for delay in sorted(todo.keys()):
            # Add any necessary delays (initial delays get stripped)
            if (curDelay > 0) and (delay > curDelay):
                p.memory_delay(delay - curDelay)
            curDelay = delay
            
            # build squid ramps, all with the same length
            now = todo[delay]
            srStart = [((n, 'Squid'), DAC1fast(pars[n]['Squid Ramp Start'])) for n in now]
            srEnd   = [((n, 'Squid'), DAC1slow(pars[n]['Squid Ramp End'  ])) for n in now]
            srZeros = [((n, 'Squid'), DAC1slow(pars[n]['Squid Zero Bias' ])) for n in now]
            maxRamp = max(MIN_DELAY, max(pars[n]['Squid Ramp Time'] for n in now))
            timers = list(now)
            
            # add commands to packet
            p.memory_bias_commands(srStart, MIN_DELAY*us)
            p.memory_start_timer(timers)
            p.memory_bias_commands(srEnd, maxRamp*us)
            p.memory_bias_commands(srZeros, MIN_DELAY*us)
            p.memory_stop_timer(timers)
            curDelay += 4.68 + maxRamp

        # reset all biases lines to zero and idle for some time
        # TODO: should have a parameter for turning off the voltage on each channel
        setFluxZero = [((n, 'Flux'), DAC1fast(0)) for n in qubits]
        setSquidZero = [((n, 'Squid'), DAC1fast(0)) for n in qubits]
        maxIdle = max(MIN_DELAY, max(pars[n]['Idle Time'] for n in qubits))
        p.memory_bias_commands(setFluxZero + setSquidZero, maxIdle*us)
        
        # send sequence to the qubit server
        yield p.send()
        
        returnValue([pars[n]['|1>-State Cutoff'] for n in qubits])

        
__server__ = QubitBiasServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
