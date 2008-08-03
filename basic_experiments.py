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

from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import Unit, mV, ns, deg, MHz, V

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from math import log

GLOBALPARS = [ "Stats" ];

SCURVEPARS =       [("Measure Offset",            "ns" ),
              
                     "Measure Pulse Amplitude",
                    ("Measure Pulse Top Length",  "ns" ),
                    ("Measure Pulse Tail Length", "ns" )]

SPECTROSCOPYPARS = SCURVEPARS + \
                   [("Microwave Offset",          "ns" ),
                    ("Resonance Frequency",       "GHz"),
                    ("Spectroscopy Pulse Length", "ns" ),
                    ("Spectroscopy Power",        "dBm")]

TOPHATPARS =       SCURVEPARS + \
                   [("Microwave Offset",          "ns" ),
                    ("Resonance Frequency",       "GHz"),
                    ("Sideband Frequency",        "GHz"),
                    ("Carrier Power",             "dBm"), 
                    ("Microwave Pulse Length",    "ns" ),
                     "Microwave Pulse Amplitude",
                    ("Measure Pulse Delay",       "ns" )]

SLEPIANPARS =      TOPHATPARS + \
                   [("Microwave Pulse Phase",     "rad")]

TWOSLEPIANPARS =   SLEPIANPARS + \
                   [("Second Pulse Length",       "ns" ),
                    ("Second Pulse Delay",        "ns" ),
                     "Second Pulse Amplitude",
                    ("Second Pulse Phase",        "rad"),
                    ("Second Sideband Frequency", "GHz")]



class NeedOneQubitError(T.Error):
    """Must select a single qubit experiment"""
    code = 1


class NeedTwoQubitsError(T.Error):
    """Must select a two qubit experiment"""
    code = 2


def analyzeData(cutoffs, data):
    states = 2**len(cutoffs)
    counts = [0.0]*states
    total  = len(data[0])
    for pid in range(total):
        n = 0
        for qid in range(len(data)):
            if (data[qid][pid]/25.0>abs(cutoffs[qid][1])) ^ (cutoffs[qid][1]<0):
                n+=2**qid
        counts[n]+=1.0
    return [c*100.0/float(total) for c in counts[1:]]

class BEServer(LabradServer):
    name = 'Basic Experiments'

    def initServer(self):
        self.Contexts=[]

    def getContext(self):
        if len(self.Contexts):
            return self.Contexts.pop()
        else:
            return self.client.context()

    def returnContext(self, ctxt):
        self.Contexts.append(ctxt)
                  
    def getQubits(self, ctxt):
        return self.client.qubits.experiment_involved_qubits(context=ctxt)

    @inlineCallbacks
    def readParameters(self, c, globalpars, qubits, qubitpars):
        # Make a new packet for the registry
        p = self.client.registry.packet(context = c.ID)
        # Load global parameters
        for parameter in globalpars:
            if isinstance(parameter, tuple):
                name, units = parameter
                # Load setting with units
                p.get(name, 'v[%s]' % units, key=name)
            else:
                # Load setting without units
                p.get(parameter, key=parameter)
        # Load qubit specific parameters
        for qubit in qubits:
            # Change into qubit directory
            p.cd(qubit, key=False)
            for parameter in qubitpars:
                if isinstance(parameter, tuple):
                    name, units = parameter
                    # Load setting with units
                    p.get(name, 'v[%s]' % units, key=(qubit, name))
                else:
                    # Load setting without units
                    p.get(parameter, key=(qubit, parameter))
            # Change back to root directory
            p.cd(1, key=False)
        # Get parameters
        ans = yield p.send()
        # Build and return parameter dictionary
        result = {}
        for key in ans.settings.keys():
            if key!="cd":
                result[key]=ans[key]
        returnValue(result)


    @setting(1, 'Squid Step', ctxt=['ww'], returns=['*2v'])
    def squid_steps(self, c, ctxt):
        """Runs a Squid Steps Sequence for a single Readout Bias"""
        # Make sure we have a single qubit experiment selected
        qubits = yield self.getQubits(ctxt)
        if len(qubits)!=1:
            raise NeedOneQubitError()
        # Get name of qubit
        qubit = qubits[0]

        # Grab one context for each run for pipelining
        ctxtneg = self.getContext()
        ctxtpos = self.getContext()

        # Set up qubit reset parameters for negative and positive reset
        p = self.client.registry.packet(context=ctxtneg)
        p.duplicate_context(c.ID)
        p.get     ('Stats')
        p.cd      (qubit)
        p.override('Operating Bias', -2.5*V)
        p.cd      (1)
        rn = p.send()
        qn = self.client.qubits.duplicate_context(ctxt, context=ctxtneg)

        p = self.client.registry.packet(context=ctxtpos)
        p.duplicate_context(c.ID)
        p.cd      (qubit)
        p.override('Operating Bias', 2.5*V)
        p.cd      (1)
        rp = p.send()
        qp = self.client.qubits.duplicate_context(ctxt, context=ctxtpos)

        # Add Squid Steps sequence to Qubit Server using Qubit Bias Server
        ans = yield rn
        yield qn
        p = self.client.qubit_bias.packet(context = ctxtneg)
        p.initialize_qubits()
        p.readout_qubits()
        bn = p.send()
        stats = ans.get
        
        yield rp
        yield qp
        p = self.client.qubit_bias.packet(context = ctxtpos)
        p.initialize_qubits()
        p.readout_qubits()
        bp = p.send()

        # Run Qubits
        yield bn
        dn = self.client.qubits.run(stats, context = ctxtneg)

        yield bp
        dp = self.client.qubits.run(stats, context = ctxtpos)

        # Get switching data
        datan = (yield dn)[0]
        datap = (yield dp)[0]

        data = [[n/25.0, p/25.0] for n, p in zip(datan, datap)]

        returnValue(data)


    @inlineCallbacks
    def run_step_edge(self, c, ctxt):
        # Get statistics
        stats = yield self.client.registry.get('Stats', context=c.ID)

        # Set up qubit experiment
        yield self.client.qubits.duplicate_context(ctxt, context=c.ID)

        # Initialize qubits
        yield self.client.qubit_bias.initialize_qubits(context = c.ID)

        # Run SRAM to sync up boards
        yield self.client.qubits.memory_call_sram(context=c.ID)
        
        # Readout qubits
        cutoffs = yield self.client.qubit_bias.readout_qubits(context = c.ID)

        # Run experiment
        data = yield self.client.qubits.run(stats, context = c.ID)

        returnValue((cutoffs, data))


    @setting(10, 'Step Edge (Switching Data)', ctxt=['ww'], returns=['*2v'])
    def step_edge_switch(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        raw switching data as a scatter plot like Squid Step does"""
        # Take data
        cutoffs, data = yield self.run_step_edge(c, ctxt)

        # Convert to us
        dat = []
        for pid in range(len(data[0])):
            d = []
            for qid in range(len(data)):
                d.append(data[qid][pid]/25.0)
            dat.append(d)

        returnValue(dat)


    @setting(11, 'Step Edge (Probability)', ctxt=['ww'], returns=['*v'])
    def step_edge_prob(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        tunneling probabilities"""
        # Take data
        cutoffs, data = yield self.run_step_edge(c, ctxt)

        # Convert to probability
        returnValue(analyzeData(cutoffs, data))


    @inlineCallbacks
    def init_qubits(self, c, ctxt, globalpars, qubitpars):
        # Grab list of qubits
        qubits = yield self.getQubits(ctxt)

        # Get experiment parameters
        pars = yield self.readParameters(c, globalpars, qubits, qubitpars)
        
        # Set up qubit experiment
        yield self.client.qubits.duplicate_context(ctxt, context=c.ID)

        # Initialize qubits
        yield self.client.qubit_bias.initialize_qubits(context = c.ID)

        # Begin SRAM packet
        p = self.client.qubits.packet(context=c.ID)
        # Add Trigger
        for qid, qname in enumerate(qubits):
            p.sram_trigger_pulse(('Trigger', qid+1), 20*ns)

        returnValue((qubits, pars, p))


    @inlineCallbacks
    def run_qubits(self, c, p, stats):
        # Setup SRAM
        p.memory_call_sram()
        yield p.send()
        
        # Readout qubits
        cutoffs = yield self.client.qubit_bias.readout_qubits(context = c.ID)

        # Run experiment
        data = yield self.client.qubits.run(stats, context = c.ID)

        returnValue(analyzeData(cutoffs, data))


    @setting(20, 'S-Curve', ctxt=['ww'], returns=['*v'])
    def s_curve(self, c, ctxt):
        """Runs an S-Curve Sequence"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SCURVEPARS)

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Add Measure Delay
            p.sram_analog_delay (('Measure', qid+1), 50*ns+pars[(qname, 'Measure Offset')])
            
            # Measure Pulse
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(30, 'Spectroscopy', ctxt=['ww'], returns=['*v'])
    def spectroscopy(self, c, ctxt):
        """Runs a Spectroscopy Sequence"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SPECTROSCOPYPARS)

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Add Microwave Pulse
            p.experiment_turn_off_deconvolution(('uWaves', qid+1))
            p.experiment_set_anritsu(('uWaves', qid+1), pars[(qname, 'Resonance Frequency')],
                                                        pars[(qname, 'Spectroscopy Power' )])
            p.sram_iq_delay         (('uWaves', qid+1), pars[(qname, 'Microwave Offset')]+50*ns)
            p.sram_iq_envelope      (('uWaves', qid+1), [1.0]*int(pars[(qname, 'Spectroscopy Pulse Length')]), 0.0, 0.0)
            
            # Add Measure Delay
            p.sram_analog_delay (('Measure', qid+1), 50*ns+pars[(qname, 'Measure Offset')]+ \
                                                           pars[(qname, 'Spectroscopy Pulse Length')])
            
            # Measure Pulse
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(40, 'TopHat Pulse', ctxt=['ww'], returns=['*v'])
    def tophat(self, c, ctxt):
        """Runs a Sequence with a single TopHat pulse (good for Rabis)"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, TOPHATPARS)

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Add Microwave Pulse
            p.experiment_set_anritsu(('uWaves', qid+1), pars[(qname, 'Resonance Frequency')]- \
                                                        pars[(qname, 'Sideband Frequency')],
                                                        pars[(qname, 'Carrier Power' )])
            p.sram_iq_delay         (('uWaves', qid+1), pars[(qname, 'Microwave Offset')]+50*ns)
            pulse = [pars[(qname, 'Microwave Pulse Amplitude')]]*int(pars[(qname, 'Microwave Pulse Length')])
            p.sram_iq_envelope      (('uWaves', qid+1), pulse, float(pars[(qname, 'Sideband Frequency')])*1000.0, 0.0)
            
            # Add Measure Delay
            p.sram_analog_delay (('Measure', qid+1), 50*ns+pars[(qname, 'Measure Offset')]+ \
                                                           pars[(qname, 'Microwave Pulse Length')]+ \
                                                           pars[(qname, 'Measure Pulse Delay')])
            
            # Measure Pulse
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(50, 'Slepian Pulse', ctxt=['ww'], returns=['*v'])
    def slepian(self, c, ctxt):
        """Runs a Sequence with a single Slepian pulse (good for Power Rabis, T1, 2 Qubit Coupling, etc.)"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SLEPIANPARS)

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Add Microwave Pulse
            p.experiment_set_anritsu(('uWaves',  qid+1), pars[(qname, 'Resonance Frequency'      )]- \
                                                         pars[(qname, 'Sideband Frequency'       )],
                                                         pars[(qname, 'Carrier Power'            )])
            p.sram_iq_delay         (('uWaves',  qid+1), pars[(qname, 'Microwave Offset'         )]+50*ns)
            p.sram_iq_slepian       (('uWaves',  qid+1), pars[(qname, 'Microwave Pulse Amplitude')],
                                                         pars[(qname, 'Microwave Pulse Length'   )],
                                                   float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                         pars[(qname, 'Microwave Pulse Phase'    )])
            # Add Measure Delay
            p.sram_analog_delay     (('Measure', qid+1), pars[(qname, 'Measure Offset'           )]+ \
                                                         pars[(qname, 'Microwave Pulse Length'   )]+ \
                                                         pars[(qname, 'Measure Pulse Delay'      )]+50*ns)
            # Measure Pulse
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(60, 'Two Slepian Pulses', ctxt=['ww'], returns=['*v'])
    def twoslepian(self, c, ctxt):
        """Runs a Sequence with two Slepian pulses"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, TWOSLEPIANPARS)

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Add Microwave Pulse
            p.experiment_set_anritsu(('uWaves',  qid+1), pars[(qname, 'Resonance Frequency'      )]- \
                                                         pars[(qname, 'Sideband Frequency'       )],
                                                         pars[(qname, 'Carrier Power'            )])
            p.sram_iq_delay         (('uWaves',  qid+1), pars[(qname, 'Microwave Offset'         )]+50*ns)
            p.sram_iq_slepian       (('uWaves',  qid+1), pars[(qname, 'Microwave Pulse Amplitude')],
                                                         pars[(qname, 'Microwave Pulse Length'   )],
                                                   float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                         pars[(qname, 'Microwave Pulse Phase'    )])
            p.sram_iq_delay         (('uWaves',  qid+1), pars[(qname, 'Second Pulse Delay'       )])
            p.sram_iq_slepian       (('uWaves',  qid+1), pars[(qname, 'Second Pulse Amplitude'   )],
                                                         pars[(qname, 'Second Pulse Length'      )],
                                                   float(pars[(qname, 'Second Sideband Frequency')])*1000.0,
                                                         pars[(qname, 'Second Pulse Phase'       )])
            # Add Measure Delay
            p.sram_analog_delay     (('Measure', qid+1), pars[(qname, 'Measure Offset'           )]+ \
                                                         pars[(qname, 'Microwave Pulse Length'   )]+ \
                                                         pars[(qname, 'Second Pulse Delay'       )]+ \
                                                         pars[(qname, 'Second Pulse Length'      )]+ \
                                                         pars[(qname, 'Measure Pulse Delay'      )]+50*ns)
            # Measure Pulse
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)


    @setting(100000, 'Kill')
    def kill(self, c, context):
        reactor.callLater(1, reactor.stop);
        

__server__ = BEServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
