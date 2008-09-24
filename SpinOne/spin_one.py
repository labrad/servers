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
from labrad.units  import Unit, mV, ns, deg, MHz, V

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from math import log
import numpy

def analyzeData(cutoffs, data):
    """Analyze timing data coming from the GHz DACs.

    Takes an array of switching data indexed by qubit# and rep#.
    Returns a list of arrays of probability |i> for each state i (as binary).
    """
    nQubits = len(cutoffs)
    states = 2**len(cutoffs)
    data = data.T # indexed by [rep#, qubit#]
    total = data.shape[0]
    cutoffNums = numpy.array([c[1] for c in cutoffs])
    isOne = (data/25.0 > abs(cutoffNums)) ^ (cutoffNums < 0)
    state = sum(2**qid * isOne[:,qid] for qid in range(nQubits))
    counts = [sum(state==s) for s in range(states)]
    return [c*100.0/float(total) for c in counts[1:]]

class SpinOneServer(LabradServer):
    """Sequences for simulating a spin-1 particle."""
    name = 'Spin One'
    
    @inlineCallbacks
    def readParameters(self, c, root=None, path=None, listing=None):
        """Load parameters needed for an experiment from the registry.

        We load a set of global parameters, as well as a set of
        qubit parameters for each qubit in the experiment.
        """
        if root is None:
            # get current path and directory listing
            p = self.client.registry.packet(context=c.ID)
            p.cd(key='path')
            p.dir(key='listing')
            ans = yield p.send()
            path = root = ans.path.aslist
            listing = ans.listing
        dirs, keys = listing
        p = self.client.registry.packet(context=c.ID)
        p.cd(path)
        for d in dirs:
            p.cd(d).dir(key=d).cd(1)
        for k in keys:
            p.get(k, key=k)
        p.cd(root)
        ans = yield p.send()
        params = {}
        for d in dirs:
            # fire off subdirectory reads
            params[d] = self.readParameters(c, root, path + [d], ans[d])
        for k in keys:
            params[k] = ans[k]
        for d in dirs:
            # wait for subdirectory reads to complete
            params[d] = yield params[d]
        returnValue(params)


    @inlineCallbacks
    def initExperiment(self, c, ctxt, globalPars, qubitPars):
        """Initialize the qubit server in this context and load needed parameters."""
        # set up experiment and get list of qubits
        p = self.client.qubits.packet(context=c.ID)
        p.duplicate_context(ctxt)
        p.experiment_involved_qubits(key='qubits')
        ans = yield p.send()
        qubits = ans['qubits']

        # load parameters needed for this experiment
        pars = yield self.readParameters(c)

        returnValue((qubits, pars))

    @setting(60, 'Multi-State Visibility', ctxt=['ww'], returns=['*v'])
    def multi_state(self, c, ctxt):
        """Runs a Sequence with two Slepian pulses"""
        qubit_server = self.client.qubits
        bias_server = self.client.qubit_bias
        Nstates = 3
        
        # initialize experiment
        qubits, pars = yield self.initExperiment(c, ctxt, GLOBALPARS, MULTISTATEPARS)
        stats = pars['Stats']

        # run a sequence at each measure pulse
        for i in range(Nstates):
            # initialize qubits
            yield bias_server.initialize_qubits(context=c.ID)

            p = qubit_server.packet(context=c.ID)

            # build SRAM for each qubit
            for qid, qname in enumerate(qubits):
                d = pars[qname]

                # extract parameters
                freq = d['Resonance Frequency'] - d['Sideband Frequency']
                power = d['Carrier Power']

                toffset = d['Microwave Offset'] + 50*ns

                amp0 = d['Microwave Pulse Amplitude']
                len0 = d['Microwave Pulse Length']
                df0 = float(d['Sideband Frequency']) * 1000.0
                phase0 = d['Microwave Pulse Phase']

                delay = d['Second Pulse Delay']

                amp1 = d['Second Pulse Amplitude']
                len1 = d['Second Pulse Length']
                df1 = float(d['Second Sideband Frequency']) * 1000.0
                phase1 = d['Second Pulse Phase']

                measTime = len0 + delay + len1 + d['Measure Offset']
                measTop  = int(d['Measure Pulse Top Length'])
                measTail = int(d['Measure Pulse Tail Length'])
                measAmp  = float(d['Measure Pulse Amplitude %d' % (i+1)])/1000.0
                measPuls = [measAmp]*measTop + [(measTail - t - 1)*measAmp/measTail for t in range(measTail)]

                # add trigger pulse
                trig = ('Trigger', qid+1)
                p.sram_trigger_pulse(trig, 20*ns)
                
                # add microwave pulses
                uw = ('uWaves', qid+1)
                p.experiment_set_anritsu(uw, freq, power)
                p.sram_iq_delay(uw, toffset)
                p.sram_iq_slepian(uw, amp0, len0, df0, phase0)
                p.sram_iq_delay(uw, delay)
                p.sram_iq_slepian(uw, amp1, len1, df1, phase1)
                
                # add measure pulse
                meas = ('Measure', qid+1)
                p.sram_analog_delay(meas, toffset)
                p.sram_analog_delay(meas, measTime)
                p.sram_analog_data(meas, measPuls)

            # setup SRAM
            p.memory_call_sram()
            yield p.send()
            
            # readout qubits
            cutoffs = yield bias_server.readout_qubits(context=c.ID)

        data = yield qubit_server.run(stats, context=c.ID)
        data = data.asarray.reshape(1, stats, Nstates) # deinterlace
        results = [analyzeData(cutoffs, data[:,:,op])[0] for op in range(Nstates)]
        returnValue(results)
        

__server__ = SpinOneServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
