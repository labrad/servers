#!c:\python25\python.exe

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

from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import us, mV

from twisted.python         import log
from twisted.internet       import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

INIT_PARAMETERS = [('Reset Bias Low',          'v[mV]', -1000.0*mV),
                   ('Reset Bias High',         'v[mV]', -1000.0*mV),
                   ('Reset Settling Time',     'v[us]',     4.3*us),
                   ('Reset Cycles',            'w',      long(0)  ),
                   ('Operating Bias',          'v[mV]',    50.0*mV),
                   ('Operating Settling Time', 'v[us]',    40.0*us), 
                   ('Squid Zero Bias',         'v[mV]',    40.0*us)]

READ_PARAMETERS = [('Readout Bias',            'v[mV]',  -500.0*mV),
                   ('Readout Settling Time',   'v[us]',    10.0*us),
                   ('Squid Ramp Delay',        'v[us]',     0.0*us),
                   ('Squid Ramp Start',        'v[mV]',   500.0*mV),
                   ('Squid Ramp End',          'v[mV]',  1500.0*mV),
                   ('Squid Ramp Time',         'v[us]',    15.0*us),
                   ('Squid Zero Bias',         'v[mV]',     0.0*mV),
                   ('Idle Time',               'v[us]',     4.3*us),
                   ('|1>-State Cutoff',        'v[us]',    10.0*us)]

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

def getCMD(DAC, value):
    return DAC*0x10000 + 0x60000 + (int((value+2500.0)*65535.0/5000.0) & 0x0FFFF)


class QubitBiasServer(LabradServer):
    """Creates basic sequences for controlling qubit bias.

    These are standard sequences for any qubit experiment, such as
    resetting and reading out by ramping the measurement squid.
    """
    name = 'Qubit Bias'
    sendTracebacks = False
                  
    def getQubits(self, c):
        return self.client.qubits.experiment_involved_qubits(context=c.ID)

    @inlineCallbacks
    def readParameters(self, c, qubits, parameters):
        # Make a new packet for the registry
        p = self.client.registry.packet()
        # Copy current directory and overrides from client context
        p.duplicate_context(c.ID)
        for qubit in qubits:
            # Change into qubit directory
            p.cd([qubit, 'bias'], True)
            for parameter in parameters:
                # Load setting
                name, typ, default = parameter
                p.get(name, typ, True, default, key=(qubit, name))
            # Change back to root directory
            p.cd(2)
        # Get parameters
        ans = yield p.send()
        # Build and return parameter dictionary
        result = {}
        for key in ans.settings.keys():
            if isinstance(key, tuple):
                result[key]=float(ans[key])
        returnValue(result)


    @setting(100, 'Initialize Qubits', returns=['*(sv[mV]): Operating Biases by Qubit'])
    def initialize(self, c):
        """Send qubit initialization commands to Qubit Server"""
        qubits = yield self.getQubits(c)
        pars   = yield self.readParameters(c, qubits, INIT_PARAMETERS)
        
        # Generate Memory Building Blocks
        initreset = []
        reset1    = []
        reset2    = []
        setop     = []
        for qid, qname in enumerate(qubits):
            # Set Flux to Reset Low and Squid to Zero Bias
            initreset.extend([(('Flux',  qid+1), DAC1fast(pars[(qname, 'Reset Bias Low' )])),
                              (('Squid', qid+1), DAC1fast(pars[(qname, 'Squid Zero Bias')]))])
            # Set Flux to Reset High
            reset1.append   ( (('Flux',  qid+1), DAC1fast(pars[(qname, 'Reset Bias High')])))
            # Set Flux to Reset Low
            reset2.append   ( (('Flux',  qid+1), DAC1fast(pars[(qname, 'Reset Bias Low' )])))
            # Set Flux to Operating Bias
            setop.append    ( (('Flux',  qid+1), DAC1fast(pars[(qname, 'Operating Bias' )])))
            
        # Find maximum number of reset cycles
        maxcount         =          max(pars[(qubit, 'Reset Cycles'           )] for qubit in qubits)
        # Find maximum Reset Settling Time
        maxresetsettling = max(4.3, max(pars[(qubit, 'Reset Settling Time'    )] for qubit in qubits))
        # Find maximum Bias Settling Time
        maxbiassettling  = max(4.3, max(pars[(qubit, 'Operating Settling Time')] for qubit in qubits))

        # Upload Memory Commands
        p = self.client.qubits.packet(context=c.ID)
        p.memory_bias_commands(initreset, maxresetsettling*us)
        for a in range(int(maxcount)):
            p.memory_bias_commands(reset1, maxresetsettling*us)
            p.memory_bias_commands(reset2, maxresetsettling*us)
        p.memory_bias_commands(setop, maxbiassettling*us)
        yield p.send()

        returnValue([(qubit, pars[(qubit, 'Operating Bias')]) for qubit in qubits])


    @setting(101, 'Readout Qubits', returns=['*(sv[us]): |1>-State Cutoffs by Qubit (negative if |1> switches BEFORE |0>)'])
    def readout(self, c):
        """Send qubit readout commands to Qubit Server"""
        qubits = yield self.getQubits(c)
        pars   = yield self.readParameters(c, qubits, READ_PARAMETERS)

        # Build TODO List based on requested Squid Ramp Delays
        setreadout = []
        setzero    = []
        todo       = {}
        for qid, qname in enumerate(qubits):
            delay = pars[(qname, 'Squid Ramp Delay')]
            if delay in todo:
                todo[delay].append((qid, qname))
            else:
                todo[delay]=      [(qid, qname)]
            # Build Readout Bias Commands
            setreadout.append( (('Flux',  qid+1), DAC1fast(pars[(qname, 'Readout Bias')])))
            setzero.extend   ([(('Flux',  qid+1), DAC1fast(0)),
                               (('Squid', qid+1), DAC1fast(0))])
            
        # Find maximum Readout Settling Time
        maxsettling  = max(4.3, max(pars[(qubit, 'Readout Settling Time')] for qubit in qubits))

        # Build and send memory commands
        p = self.client.qubits.packet(context=c.ID)
        p.memory_bias_commands(setreadout, maxsettling*us)
        curdelay = 0.0;
        for key in sorted(todo.keys()):
            # Add any necessary delays (initial delays get stripped)
            if (curdelay>0) and (key>curdelay):
                p.memory_delay(key-curdelay)
            curdelay = key
            # Add squid ramp
            srstart   = []
            timers    = []
            srend     = []
            srzeros   = []
            for qid, qname in todo[key]:
                # Set Squid Bias to Ramp Start
                srstart.append((('Squid', qid+1), DAC1fast(pars[(qname, 'Squid Ramp Start')])))
                # Start/Stop Timer
                timers.append   (         qid+1)
                # Set Squid Bias to Ramp End
                srend.append  ((('Squid', qid+1), DAC1slow(pars[(qname, 'Squid Ramp End'  )])))
                # Set Flux to Reset Low and Squid to Zero
                srzeros.append((('Squid', qid+1), DAC1fast(pars[(qname, 'Squid Zero Bias' )])))
                
            # Find maximum Ramp Time
            maxramp  = max(4.3, max(pars[(qname, 'Squid Ramp Time')] for qid, qname in todo[key]))

            # Send Memory Commands
            p.memory_bias_commands(srstart,   4.3*us)
            p.memory_start_timer  (timers)
            p.memory_bias_commands(srend, maxramp*us)
            p.memory_bias_commands(srzeros,   4.3*us)
            p.memory_stop_timer   (timers)
            curdelay += 4.68 + maxramp

        # Find maximum Idle Time
        maxidle  = max(4.3, max(pars[(qubit, 'Idle Time')] for qubit in qubits))
        
        # Go to 0V on all lines
        p.memory_bias_commands(setzero, maxidle*us)
        yield p.send()
        
        returnValue([(qubit, pars[(qubit, '|1>-State Cutoff')]) for qubit in qubits])

        

__server__ = QubitBiasServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
