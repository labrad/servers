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

INIT_PARAMETERS = [('Reset Bias Low',          'mV'),
                   ('Reset Bias High',         'mV'),
                   ('Reset Settling Time',     'us'),
                    'Reset Cycles',
                   ('Operating Bias',          'mV'),
                   ('Operating Settling Time', 'us'),
                   ('Squid Zero Bias',         'mV')]

READ_PARAMETERS = [('Readout Bias',            'mV'),
                   ('Readout Settling Time',   'us'),
                   ('Squid Ramp Delay',        'us'),
                   ('Squid Ramp Start',        'mV'),
                   ('Squid Ramp End',          'mV'),
                   ('Squid Ramp Time',         'us'),
                   ('Squid Zero Bias',         'mV'),
                   ('|1>-State Cutoff',        'us')]


def getCMD(DAC, value):
    return DAC*0x10000 + 0x60000 + (int((value+2500.0)*65535.0/5000.0) & 0x0FFFF)


class QubitBiasServer(LabradServer):
    name = 'Qubit Bias'
    sendTracebacks = True
                  
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
            p.cd(qubit)
            for parameter in parameters:
                if isinstance(parameter, tuple):
                    name, units = parameter
                    # Load setting with units
                    p.get(name, 'v[%s]' % units, key=(qubit, name))
                else:
                    # Load setting without units
                    p.get(parameter, key=(qubit, parameter))
            # Change back to root directory
            p.cd(1)
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
        dac1s     = []
        reset1    = []
        reset2    = []
        setop     = []
        for qid, qname in enumerate(qubits):
            # Set Flux to Reset Low and Squid to Zero
            initreset.extend([(('Flux',  qid+1), getCMD(1, pars[(qname, 'Reset Bias Low' )])),
                              (('Squid', qid+1), getCMD(1, pars[(qname, 'Squid Zero Bias')]))])
            # Set Bias DACs to DAC 1
            dac1s.extend    ([(('Flux',  qid+1), 0x50001), (('Squid', qid+1), 0x50001)])
            # Set Flux to Reset Low
            reset1.append   ( (('Flux',  qid+1), getCMD(1, pars[(qname, 'Reset Bias Low' )])))
            # Set Flux to Reset High
            reset2.append   ( (('Flux',  qid+1), getCMD(1, pars[(qname, 'Reset Bias High')])))
            # Set Flux to Operating Bias
            setop.append    ( (('Flux',  qid+1), getCMD(1, pars[(qname, 'Operating Bias' )])))
            
        # Find maximum number of reset cycles
        maxcount         =        max(pars[(qubit, 'Reset Cycles'           )] for qubit in qubits)
        # Find maximum Reset Settling Time
        maxresetsettling = max(7, max(pars[(qubit, 'Reset Settling Time'    )] for qubit in qubits))
        # Find maximum Bias Settling Time
        maxbiassettling  = max(7, max(pars[(qubit, 'Operating Settling Time')] for qubit in qubits))

        # Upload Memory Commands
        p = self.client.qubits.packet(context=c.ID)
        p.memory_bias_commands(initreset, 7.0*us)
        p.memory_bias_commands(dac1s, maxresetsettling*us)
        for a in range(int(maxcount)):
            p.memory_bias_commands(reset2, maxresetsettling*us)
            p.memory_bias_commands(reset1, maxresetsettling*us)
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
            setreadout.append( (('Flux',  qid+1), getCMD(1, pars[(qname, 'Readout Bias')])))
            setzero.extend   ([(('Flux',  qid+1), getCMD(1, 0)),
                               (('Squid', qid+1), getCMD(1, 0))])
        # Find maximum Readout Settling Time
        maxsettling  = max(7, max(pars[(qubit, 'Readout Settling Time')] for qubit in qubits))

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
            dac1slow  = []
            timers    = []
            srend     = []
            srzeros   = []
            dac1fast  = []
            for qid, qname in todo[key]:
                # Set Squid Bias to Ramp Start
                srstart.append ((('Squid', qid+1), getCMD(1, pars[(qname, 'Squid Ramp Start')])))
                # Set Bias DACs to DAC 1 slow
                dac1slow.append((('Squid', qid+1), 0x50002))
                # Start/Stop Timer
                timers.append    (         qid+1)
                # Set Squid Bias to Ramp End
                srend.append   ((('Squid', qid+1), getCMD(1, pars[(qname, 'Squid Ramp End'  )])))
                # Set Flux to Reset Low and Squid to Zero
                srzeros.append ((('Squid', qid+1), getCMD(1, pars[(qname, 'Squid Zero Bias' )])))
                # Set Bias DACs to DAC fast
                dac1fast.append((('Squid', qid+1), 0x50001))
                
            # Find maximum Ramp Time
            maxramp  = max(7, max(pars[(qubit, 'Squid Ramp Time')] for qubit in qubits))

            # Send Memory Commands
            p.memory_bias_commands(srstart,   7.0*us)
            p.memory_bias_commands(dac1slow,  5.0*us)
            p.memory_start_timer  (timers)
            p.memory_bias_commands(srend, maxramp*us)
            p.memory_bias_commands(srzeros,   7.0*us)
            p.memory_stop_timer   (timers)
            p.memory_bias_commands(dac1fast,  5.0*us)
            curdelay += 24.08 + maxramp
        p.memory_bias_commands(setzero, maxsettling*us)
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
