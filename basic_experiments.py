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
from labrad.units  import Unit, mV, ns, deg, MHz, V, GHz, rad

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from math import log
import numpy

GLOBALPARS = [("Stats", "w", long(300))];

dBm = Unit('dBm')
SCURVEPARS =       [("Measure Offset",            "Timing",        "Measure Offset",      "v[ns]",   50.0*ns ),
                    ("Measure Pulse Amplitude",   "Measure Pulse", "Amplitude",           "v[mV]",  500.0*mV ),
                    ("Measure Pulse Top Length",  "Measure Pulse", "Top Length",          "v[ns]",    5.0*ns ),
                    ("Measure Pulse Tail Length", "Measure Pulse", "Tail Length",         "v[ns]",   15.0*ns )]

SPECTROSCOPYPARS = SCURVEPARS + \
                   [("Microwave Offset",          "Timing",        "Microwave Offset",    "v[ns]",   50.0*ns ),
                    ("Spectroscopy Pulse Length", "Spectroscopy",  "Pulse Length",        "v[ns]",   2000*ns ),
                    ("Resonance Frequency",       "Spectroscopy",  "Frequency",           "v[GHz]",   6.5*GHz),
                    ("Spectroscopy Power",        "Spectroscopy",  "Power",               "v[dBm]", -30.0*dBm)]

SPEC2DPARS =       SCURVEPARS + \
                   [("Microwave Offset",          "Timing",        "Microwave Offset",    "v[ns]",   50.0*ns ),
                    ("Spectroscopy Pulse Length", "Spectroscopy",  "Pulse Length",        "v[ns]",   2000*ns ),
                    ("Operating Bias",            "Bias",          "Operating Bias",      "v[V]",    0.05*V  ),
                    ("Frequency Shift",           "Spectroscopy",  "dFrequency",          "v[GHz]",   6.5*GHz),
                    ("Measure Calibration",       "Measure Pulse", "Calibration",         "vv",     (1.0,1.0)),
                    ("Frequency Calibration",     "Spectroscopy",  "Calibration",         "vvv",(1.0,1.0,1.0)),
                    ("Spectroscopy Power",        "Spectroscopy",  "Power",               "v[dBm]", -30.0*dBm)]

TOPHATPARS =       SCURVEPARS + \
                   [("Microwave Offset",          "Timing",        "Microwave Offset",    "v[ns]",   50.0*ns ),
                    ("Carrier Power",             "Microwaves",    "Carrier Power",       "v[dBm]",   2.7*dBm), 
                    ("Sideband Frequency",        "Microwaves",    "Sideband Frequency",  "v[GHz]",-150.0*MHz),
                    ("Microwave Pulse Length",    "Pulse 1",       "Length",              "v[ns]",   16.0*ns ),
                    ("Microwave Pulse Amplitude", "Pulse 1",       "Amplitude",           "v[mV]",  100.0*mV ),
                    ("Resonance Frequency",       "Pulse 1",       "Frequency",           "v[GHz]",   6.5*GHz),
                    ("Measure Pulse Delay",       "Measure Pulse", "Delay",               "v[ns]",    5.0*ns )]

SLEPIANPARS =      TOPHATPARS + \
                   [("Microwave Pulse Phase",     "Pulse 1",       "Phase",               "v[rad]",   0.0*rad)]

TWOSLEPIANPARS =   SLEPIANPARS + \
                   [("Second Pulse Length",       "Pulse 2",       "Length",              "v[ns]",   16.0*ns ),
                    ("Second Pulse Delay",        "Pulse 2",       "Delay",               "v[ns]",   10.0*ns ),
                    ("Second Pulse Amplitude",    "Pulse 2",       "Amplitude",           "v[mV]",  100.0*mV ),
                    ("Second Pulse Phase",        "Pulse 2",       "Phase",               "v[rad]", 180.0*rad),
                    ("Second Frequency",          "Pulse 2",       "Frequency",           "v[GHz]", 200.0*MHz)]



class NeedOneQubitError(T.Error):
    """Must select a single qubit experiment"""
    code = 1


class NeedTwoQubitsError(T.Error):
    """Must select a two qubit experiment"""
    code = 2


def analyzeData(cutoffs, data):
    nQubits = len(cutoffs)
    states = 2**len(cutoffs)
    data = data.asarray.T # indexed by [rep#, qubit#]
    total = data.shape[0]
    cutoffNums = numpy.array([c[1] for c in cutoffs])
    isOne = (data/25.0 > abs(cutoffNums)) ^ (cutoffNums < 0)
    state = sum(2**qid * isOne[:,qid] for qid in range(nQubits))
    counts = [sum(state==s) for s in range(states)]
    return [c*100.0/float(total) for c in counts[1:]]


def analyzeDataSeparate(cutoffs, data):
    nQubits = len(cutoffs)
    data = data.asarray.T # indexed by [rep#, qubit#]
    total = data.shape[0]
    cutoffNums = numpy.array([c[1] for c in cutoffs])
    isOne = (data/25.0 > abs(cutoffNums)) ^ (cutoffNums < 0)
    counts = sum(isOne)
    return [c*100.0/float(total) for c in counts]

def analyzeDataSeparate2(cutoffs, data):
    nQubits = len(cutoffs)
    data = data.T # indexed by [rep#, qubit#]
    total = data.shape[0]
    cutoffNums = numpy.array([c[1] for c in cutoffs])
    isOne = (data/25.0 > abs(cutoffNums)) ^ (cutoffNums < 0)
    counts = sum(isOne)
    return [c*100.0/float(total) for c in counts]


class BEServer(LabradServer):
    """Provides basic experiments for bringing up a qubit."""
    name = 'Basic Experiments'
                  
    def getQubits(self, ctxt):
        return self.client.qubits.experiment_involved_qubits(context=ctxt)

    @inlineCallbacks
    def readParameters(self, c, globalpars, qubits, qubitpars):
        # Make a new packet for the registry
        p = self.client.registry.packet(context=c.ID)
        # Load global parameters
        for parameter in globalpars:
            # Load setting
            name, typ, default = parameter
            p.get(name, typ, True, default, key=name)
        # Load qubit specific parameters
        for qubit in qubits:
            # Change into qubit directory
            p.cd(qubit, True, key=False)
            for parameter in qubitpars:
                # Load setting
                name, path, key, typ, default = parameter
                p.cd(path, True, key=False)
                p.get(key, typ, True, default, key=(qubit, name))
                p.cd(1, key=False)
            # Change back to analyzeDataSeparateroot directory
            p.cd(1, key=False)
        # Get parameters
        ans = yield p.send()
        # Build and return parameter dictionary
        result = {}
        for key in ans.settings.keys():
            if key != "cd":
                result[key] = ans[key]
        returnValue(result)


    @setting(1, 'Squid Step', ctxt=['ww'], returns=['*2v'])
    def squid_steps(self, c, ctxt):
        """Runs a Squid Steps Sequence for a single Readout Bias"""
        # Make sure we have a single qubit experiment selected
        qubits = yield self.getQubits(ctxt)
        if len(qubits) != 1:
            raise NeedOneQubitError()
        # Get name of qubit
        qubit = qubits[0]
        
        # Set up qubit experiment
        yield self.client.qubits.duplicate_context(ctxt, context=c.ID)

        # Set up qubit reset for negative reset
        p = self.client.registry.packet(context=c.ID)
        p.get     ('Stats')
        p.cd      ([qubit, 'Bias'])
        p.override('Operating Bias', -2.5*V)
        p.cd      (2)
        ans = yield p.send()
        stats = ans.get

        # Add sequence for negative reset
        p = self.client.qubit_bias.packet(context=c.ID)
        p.initialize_qubits()
        p.readout_qubits()
        yield p.send()

        # Set up qubit reset for positive reset
        p = self.client.registry.packet(context=c.ID)
        p.cd      ([qubit, 'Bias'])
        p.override('Operating Bias', 2.5*V)
        p.cd      (2)
        yield p.send()

        # Add sequence for positive reset
        p = self.client.qubit_bias.packet(context=c.ID)
        p.initialize_qubits()
        p.readout_qubits()
        yield p.send()

        # Run Qubits
        data = yield self.client.qubits.run(stats, context=c.ID)

        # Process switching data
        data = data.asarray[0].reshape(stats, 2) / 25.0

        returnValue(data)


    @inlineCallbacks
    def run_step_edge(self, c, ctxt):
        cxn = self.client
        
        # Get statistics
        stats = yield cxn.registry.get('Stats', context=c.ID)

        # Set up qubit experiment
        yield cxn.qubits.duplicate_context(ctxt, context=c.ID)

        # Initialize qubits
        yield cxn.qubit_bias.initialize_qubits(context=c.ID)

        # Run SRAM to sync up boards
        yield cxn.qubits.memory_call_sram(context=c.ID)
        
        # Readout qubits
        cutoffs = yield cxn.qubit_bias.readout_qubits(context=c.ID)

        # Run experiment
        data = yield cxn.qubits.run(stats, context=c.ID)

        returnValue((cutoffs, data))


    @setting(10, 'Step Edge (Switching Data)', ctxt=['ww'], returns=['*2v'])
    def step_edge_switch(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        raw switching data as a scatter plot like Squid Step does"""
        # Take data
        cutoffs, data = yield self.run_step_edge(c, ctxt)

        # Convert to us
        # TODO: use numpy arrays here
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


    @setting(12, 'Step Edge (Probability, Separate)', ctxt=['ww'], returns=['*v'])
    def step_edge_prob_sep(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        tunneling probabilities"""
        # Take data
        cutoffs, data = yield self.run_step_edge(c, ctxt)

        # Convert to probability
        returnValue(analyzeDataSeparate(cutoffs, data))


    @inlineCallbacks
    def init_qubits(self, c, ctxt, globalpars, qubitpars):
        # Grab list of qubits
        qubits = yield self.getQubits(ctxt)

        # Get experiment parameters
        pars = yield self.readParameters(c, globalpars, qubits, qubitpars)
        
        # Set up qubit experiment
        yield self.client.qubits.duplicate_context(ctxt, context=c.ID)

        # Initialize qubits
        yield self.client.qubit_bias.initialize_qubits(context=c.ID)

        # Begin SRAM packet
        p = self.client.qubits.packet(context=c.ID)
        # Add Trigger
        for qid, qname in enumerate(qubits):
            p.sram_trigger_pulse(('Trigger', qid+1), 20*ns)

        returnValue((qubits, pars, p))

    @inlineCallbacks
    def reinit_qubits(self, c, p, qubits):
        # Setup SRAM
        p.memory_call_sram()
        yield p.send()
        
        # Readout qubits
        p = self.client.qubit_bias.packet(context=c.ID)
        p.readout_qubits()

        # Initialize qubits
        p.initialize_qubits()
        yield p.send()

        # Begin SRAM packet
        p = self.client.qubits.packet(context=c.ID)
        # Add Trigger
        for qid, qname in enumerate(qubits):
            p.sram_trigger_pulse(('Trigger', qid+1), 20*ns)

        returnValue(p)                      

    @inlineCallbacks
    def run_qubits(self, c, p, stats):
        # Setup SRAM
        p.memory_call_sram()
        yield p.send()
        
        # Readout qubits
        cutoffs = yield self.client.qubit_bias.readout_qubits(context=c.ID)

        # Run experiment
        data = yield self.client.qubits.run(stats, context=c.ID)

        returnValue(analyzeData(cutoffs, data))


    @inlineCallbacks
    def run_qubits_separate(self, c, p, stats, n=1):
        # Setup SRAM
        p.memory_call_sram()
        yield p.send()
        
        # Readout qubits
        cutoffs = yield self.client.qubit_bias.readout_qubits(context=c.ID)

        # Run experiment
        data = yield self.client.qubits.run(stats, context=c.ID)

        if n==1:
            returnValue(analyzeDataSeparate(cutoffs, data))

        data = data.asarray

        l = 1
        for s in data.shape:
            l *= s
        
        # Deinterlace data
        data = data.reshape(l/stats/n, stats, n)

        # Turn switching data into probabilities
        results = [analyzeDataSeparate2(cutoffs, data[:,:,i]) for i in range(n)]

        returnValue(results)        


    @setting(20, 'S-Curve', ctxt=['ww'], returns=['*v'])
    def s_curve(self, c, ctxt):
        """Runs an S-Curve Sequence and returns P|10..>, P|01...>, ..., P|11...>"""
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


    @setting(21, 'S-Curve Separate', ctxt=['ww'], returns=['*v'])
    def s_curve_sep(self, c, ctxt):
        """Runs an S-Curve Sequence and returns P|1xx...>, P|x1x...>, P|xx1...>, ..."""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SCURVEPARS)

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Add Measure Delay
            p.sram_analog_delay (('Measure', qid+1), 50*ns+pars[(qname, 'Measure Offset')])
            
            # Measure PulseanalyzeDataSeparate
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits_separate(c, p, pars['Stats'])
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


    @setting(31, '2D Spectroscopy', ctxt=['ww'], returns=['*v'])
    def spec2D(self, c, ctxt):
        """Runs a Spectroscopy Sequence using the Operating Bias to calculate the
        Measure Pulse Amplitude and Resonance Frequency. Returns the frequency of
        each data point."""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SPEC2DPARS)

        frqs = []

        # Build SRAM
        for qid, qname in enumerate(qubits):
            # Caluclate frequency and measure pulse amplitude
            bias = float(pars[(qname, 'Operating Bias'       )])
            fcal =       pars[(qname, 'Frequency Calibration')]
            mcal =       pars[(qname, 'Measure Calibration'  )]
            
            frq =  (float(fcal[0])*bias*bias + float(fcal[1])*bias + float(fcal[2]))**4 + float(pars[(qname, 'Frequency Shift')])
            mpa =                              float(mcal[0])*bias + float(mcal[1])
            
            # Add Microwave Pulse
            p.experiment_turn_off_deconvolution(('uWaves', qid+1))
            p.experiment_set_anritsu(('uWaves', qid+1), frq,
                                                        pars[(qname, 'Spectroscopy Power' )])
            p.sram_iq_delay         (('uWaves', qid+1), pars[(qname, 'Microwave Offset')]+50*ns)
            p.sram_iq_envelope      (('uWaves', qid+1), [1.0]*int(pars[(qname, 'Spectroscopy Pulse Length')]), 0.0, 0.0)
            
            # Add Measure Delay
            p.sram_analog_delay (('Measure', qid+1), 50*ns+pars[(qname, 'Measure Offset')]+ \
                                                           pars[(qname, 'Spectroscopy Pulse Length')])
            
            # Measure Pulse
            meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
            meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
            measamp  = mpa
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data  (('Measure', qid+1), measpuls)

            frqs.append(frq)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(frqs+data)
        

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
            pulse = [float(pars[(qname, 'Microwave Pulse Amplitude')])/1000.0]*int(pars[(qname, 'Microwave Pulse Length')])
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
            p.sram_iq_slepian       (('uWaves',  qid+1), float(pars[(qname, 'Microwave Pulse Amplitude')])/1000.0,
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
            p.sram_iq_slepian       (('uWaves',  qid+1), float(pars[(qname, 'Microwave Pulse Amplitude')])/1000.0,
                                                         pars[(qname, 'Microwave Pulse Length'   )],
                                                   float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                         pars[(qname, 'Microwave Pulse Phase'    )])
            p.sram_iq_delay         (('uWaves',  qid+1), pars[(qname, 'Second Pulse Delay'       )])
            p.sram_iq_slepian       (('uWaves',  qid+1), float(pars[(qname, 'Second Pulse Amplitude'   )])/1000.0,
                                                         pars[(qname, 'Second Pulse Length'      )],
                                                  (float(pars[(qname, 'Second Frequency'         )])- \
                                                   float(pars[(qname, 'Resonance Frequency'      )])+ \
                                                   float(pars[(qname, 'Sideband Frequency'       )]))*1000.0,
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


    @setting(100, 'Visibility', ctxt=['ww'], returns=['*v'])
    def visibility(self, c, ctxt):
        """Runs a Sequence with and without a single Slepian pulse and returns Pw(|1>), Pw/o(|1>) and Pw-Pw/o for each qubit"""

        data = []

        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SLEPIANPARS)

        # Build SRAM for |0>-state
        for qid, qname in enumerate(qubits):
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

        # Reinitialize for second data point
        p = yield self.reinit_qubits(c, p, qubits)

        # Build SRAM for |1>-state
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
        data = yield self.run_qubits_separate(c, p, pars['Stats'], 2)

        ans = []
        for off, on in zip(data[0], data[1]):
            ans.extend([off, on, on-off])
            
        returnValue(ans)


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
