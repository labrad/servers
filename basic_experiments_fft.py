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
### BEGIN NODE INFO
[info]
name = Basic Experiments FFT
version = 1.1
description = Standard qubit experiments (T1, Rabi, etc.)

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad        import types as T
from labrad.server import LabradServer, setting
from labrad.units  import Unit, mV, ns, deg, MHz, V, GHz, rad

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

import math
import numpy

import sequencesFT as SFT

GLOBALPARS = [("Stats", "w", long(300))]

dBm = Unit('dBm')
ident = lambda x: x
d1000 = lambda x: float(x)/1000.0

SCURVEPARS = [
    ("mpofs", "Timing",        "Measure Offset",     "v[ns]",   50.0*ns,  float),
    ("mpamp", "Measure Pulse", "Amplitude",          "v[mV]",  500.0*mV,  d1000),
    ("mptop", "Measure Pulse", "Top Length",         "v[ns]",    5.0*ns,  float),
    ("mptal", "Measure Pulse", "Tail Length",        "v[ns]",   15.0*ns,  float)]

SPECTROSCOPYPARS = SCURVEPARS + [
    ("uwofs", "Timing",        "Microwave Offset",   "v[ns]",   50.0*ns,  float),
    ("splen", "Spectroscopy",  "Pulse Length",       "v[ns]",   2000*ns,  float),
    ("uwfrq", "Spectroscopy",  "Frequency",          "v[GHz]",   6.5*GHz, float),
    ("sppow", "Spectroscopy",  "Power",              "v[dBm]", -30.0*dBm, float)]

SPEC2DPARS = SCURVEPARS + [
    ("uwofs", "Timing",        "Microwave Offset",   "v[ns]",   50.0*ns,  float),
    ("splen", "Spectroscopy",  "Pulse Length",       "v[ns]",   2000*ns,  float),
    ("fbias", "Bias",          "Operating Bias",     "v[V]",    0.05*V,   float),
    ("dfreq", "Spectroscopy",  "dFrequency",         "v[GHz]",   6.5*GHz, float),
    ("mpcal", "Measure Pulse", "Calibration",        "vv",     (1.0,1.0), ident),
    ("frcal", "Spectroscopy",  "Calibration",        "vvv",(1.0,1.0,1.0), ident),
    ("sppow", "Spectroscopy",  "Power",              "v[dBm]", -30.0*dBm, float)]

TOPHATPARS =       SCURVEPARS + [
    ("uwofs", "Timing",        "Microwave Offset",   "v[ns]",   50.0*ns,  float),
    ("uwpow", "Microwaves",    "Carrier Power",      "v[dBm]",   2.7*dBm, float), 
    ("sbfrq", "Microwaves",    "Sideband Frequency", "v[GHz]",-150.0*MHz, float),
    ("plen1", "Pulse 1",       "Length",             "v[ns]",   16.0*ns,  float),
    ("pamp1", "Pulse 1",       "Amplitude",          "v[mV]",  100.0*mV,  d1000),
    ("pfrq1", "Pulse 1",       "Frequency",          "v[GHz]",   6.5*GHz, float),
    ("mpdel", "Measure Pulse", "Delay",              "v[ns]",    5.0*ns,  float)]

SLEPIANPARS =      TOPHATPARS + [
    ("pphs1", "Pulse 1",       "Phase",              "v[rad]",   0.0*rad, float)]

TWOSLEPIANPARS =   SLEPIANPARS + [
    ("plen2", "Pulse 2",       "Length",             "v[ns]",   16.0*ns,  float),
    ("pdel2", "Pulse 2",       "Delay",              "v[ns]",   10.0*ns,  float),
    ("pamp2", "Pulse 2",       "Amplitude",          "v[mV]",  100.0*mV,  d1000),
    ("pphs2", "Pulse 2",       "Phase",              "v[rad]", 180.0*rad, float),
    ("pfrq2", "Pulse 2",       "Frequency",          "v[GHz]",   6.5*GHz, float)]

THREESLEPIANPARS = TWOSLEPIANPARS + [
    ("plen3", "Pulse 3",       "Length",             "v[ns]",   16.0*ns,  float),
    ("pdel3", "Pulse 3",       "Delay",              "v[ns]",   10.0*ns,  float),
    ("pamp3", "Pulse 3",       "Amplitude",          "v[mV]",  100.0*mV,  d1000),
    ("pphs3", "Pulse 3",       "Phase",              "v[rad]", 180.0*rad, float),
    ("pfrq3", "Pulse 3",       "Frequency",          "v[GHz]",   6.5*GHz, float)]

SLEPZSLEPPARS =    TWOSLEPIANPARS + [
    ("sampl", "Settling",      "Amplitude",          "*v[]",   [-0.02],   None),
    ("srate", "Settling",      "Rate",               "*v[GHz]",[0.02*GHz],None),
    ("zlen1", "Z Pulse 1",     "Length",             "v[ns]",   16.0*ns,  float),
    ("zdel1", "Z Pulse 1",     "Delay",              "v[ns]",   10.0*ns,  float),
    ("zovs1", "Z Pulse 1",     "Overshoot",          "v[mV]",    0.0*mV,  d1000),
    ("zamp1", "Z Pulse 1",     "Amplitude",          "v[mV]",  100.0*mV,  d1000)]

SLEPZZSLEPPARS =   SLEPZSLEPPARS + [
    ("zlen2", "Z Pulse 2",     "Length",             "v[ns]",   16.0*ns,  float),
    ("zdel2", "Z Pulse 2",     "Delay",              "v[ns]",   10.0*ns,  float),
    ("zovs2", "Z Pulse 2",     "Overshoot",          "v[mV]",    0.0*mV,  d1000),
    ("zamp2", "Z Pulse 2",     "Amplitude",          "v[mV]",  100.0*mV,  d1000)]



uCh = lambda i: ('uWaves', i+1)
mCh = lambda i: ('Measure', i+1)
tCh = lambda i: ('Trigger', i+1)

PADDING = 50.0

def mpFreqs(seqTime=1024):
    nfft = 2**(math.ceil(math.log(seqTime + 2*PADDING, 2))+1)
    return numpy.linspace(0, 0.5, nfft/2, endpoint=False)

def uwFreqs(seqTime=1024):
    nfft = 2**(math.ceil(math.log(seqTime + 2*PADDING, 2))+1)
    return numpy.linspace(0.5, 1.5, nfft, endpoint=False) % 1 - 0.5


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
    state = sum(2**i * isOne[:,i] for i in range(nQubits))
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
    name = 'Basic Experiments FFT'
                  
    def getQubits(self, ctxt):
        return self.client.qubits.experiment_involved_qubits(context=ctxt)

    @inlineCallbacks
    def readParameters(self, c, globalpars, qubits, qubitpars):
        p = self.client.registry.packet(context=c.ID)
        # Load global parameters
        for parameter in globalpars:
            name, typ, default = parameter
            p.get(name, typ, True, default, key=name)
        # Load qubit specific parameters
        for qubit in qubits:
            p.cd(qubit, True, key=False) # change into qubit directory
            for parameter in qubitpars:
                name, path, key, typ, default, func = parameter
                p.cd(path, True, key=False)
                p.get(key, typ, True, default, key=(qubit, name))
                p.cd(1, key=False)
            p.cd(1, key=False) # change back into root directory
        # Get parameters
        ans = yield p.send()
        # Build and return parameter dictionary
        result = {}
        for parameter in globalpars:
            name, typ, default = parameter
            result[name] = ans[name]
        for i, qubit in enumerate(qubits):
            q = result[qubit] = {}
            for parameter in qubitpars:
                name, path, key, typ, default, func = parameter
                if func is None:
                    q[name] = ans[(qubit, name)]
                else:
                    q[name] = func(ans[(qubit, name)])
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
        stats = yield cxn.registry.get('Stats', context=c.ID) # Get statistics
        yield cxn.qubits.duplicate_context(ctxt, context=c.ID) # Set up qubit experiment
        yield cxn.qubit_bias.initialize_qubits(context=c.ID) # Initialize qubits
        yield cxn.qubits.memory_call_sram(context=c.ID) # Run SRAM to sync up boards
        cutoffs = yield cxn.qubit_bias.readout_qubits(context=c.ID) # Readout qubits
        data = yield cxn.qubits.run(stats, context=c.ID) # Run experiment
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
            for i in range(len(data)):
                d.append(data[i][pid]/25.0)
            dat.append(d)

        returnValue(dat)


    @setting(11, 'Step Edge (Probability)', ctxt=['ww'], returns=['*v'])
    def step_edge_prob(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        tunneling probabilities"""
        cutoffs, data = yield self.run_step_edge(c, ctxt) # Take data
        returnValue(analyzeData(cutoffs, data)) # Convert to probability


    @setting(12, 'Step Edge (Probability, Separate)', ctxt=['ww'], returns=['*v'])
    def step_edge_prob_sep(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        tunneling probabilities"""
        cutoffs, data = yield self.run_step_edge(c, ctxt) # Take data
        returnValue(analyzeDataSeparate(cutoffs, data)) # Convert to probability


    @inlineCallbacks
    def init_qubits(self, c, ctxt, globalpars, qubitpars):
        qubits = yield self.getQubits(ctxt) # Grab list of qubits
        pars = yield self.readParameters(c, globalpars, qubits, qubitpars) # Get parameters
        yield self.client.qubits.duplicate_context(ctxt, context=c.ID) # Set up qubit experiment
        yield self.client.qubit_bias.initialize_qubits(context=c.ID) # Initialize qubits
        p = self.client.qubits.packet(context=c.ID) # Begin SRAM packet
        for i, qname in enumerate(qubits): # Add Trigger
            p.sram_trigger_pulse(tCh(i), 20*ns)
        returnValue((qubits, pars, p))

    @inlineCallbacks
    def reinit_qubits(self, c, p, qubits):
        # Finish previous sequence
        p.memory_call_sram()
        yield p.send()
        p = self.client.qubit_bias.packet(context=c.ID)
        p.readout_qubits()

        # Start next sequence
        p.initialize_qubits()
        yield p.send()
        p = self.client.qubits.packet(context=c.ID) # Begin SRAM packet
        for i, qname in enumerate(qubits): # Add Trigger
            p.sram_trigger_pulse(tCh(i), 20*ns)
        returnValue(p)                      

    @inlineCallbacks
    def run_qubits(self, c, p, stats):
        p.memory_call_sram() # Setup SRAM
        yield p.send()
        cutoffs = yield self.client.qubit_bias.readout_qubits(context=c.ID) # Readout qubits
        data = yield self.client.qubits.run(stats, context=c.ID) # Run experiment
        returnValue(analyzeData(cutoffs, data))


    @inlineCallbacks
    def run_qubits_separate(self, c, p, stats, n=1):
        p.memory_call_sram() # Setup SRAM
        yield p.send()
        cutoffs = yield self.client.qubit_bias.readout_qubits(context=c.ID) # Readout qubits
        data = yield self.client.qubits.run(stats, context=c.ID) # Run experiment

        if n == 1:
            results = analyzeDataSeparate(cutoffs, data)
        else:
            data = data.asarray
            l = 1
            for s in data.shape:
                l *= s
            data = data.reshape(l/stats/n, stats, n) # Deinterlace data
            results = [analyzeDataSeparate2(cutoffs, data[:,:,i]) for i in range(n)]
        returnValue(results)


    def uploadSram(self, p, q, i, mpSeq=None, uwSeq=None, time=1024):
        if mpSeq is not None:
            p.experiment_use_fourier_deconvolution(mCh(i), -(PADDING + q['mpofs'])*ns)
            p.sram_analog_data(mCh(i), mpSeq(mpFreqs(time)))
        if uwSeq is not None:
            p.experiment_use_fourier_deconvolution(uCh(i), -(PADDING + q['uwofs'])*ns)
            p.sram_iq_data(uCh(i), uwSeq(uwFreqs(time)), tag='(sw)*c')


    @inlineCallbacks
    def scurveExp(self, c, ctxt, runFunc):
        """Runs an S-Curve Sequence and returns P|10..>, P|01...>, ..., P|11...>"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SCURVEPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            mpSeq = SFT.rampPulse2(0, q['mptop'], q['mptal'], q['mpamp'])
            
            time = q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, time=time)

        # Run experiment and return result
        data = yield runFunc(c, p, pars['Stats'])
        returnValue(data)


    @setting(20, 'S-Curve', ctxt=['ww'], returns=['*v'])
    def s_curve(self, c, ctxt):
        """Runs an S-Curve Sequence and returns P|10..>, P|01...>, ..., P|11...>"""
        return self.scurveExp(c, ctxt, self.run_qubits)


    @setting(21, 'S-Curve Separate', ctxt=['ww'], returns=['*v'])
    def s_curve_sep(self, c, ctxt):
        """Runs an S-Curve Sequence and returns P|1xx...>, P|x1x...>, P|xx1...>, ..."""
        return self.scurveExp(c, ctxt, self.run_qubits_separate)
  

    @setting(30, 'Spectroscopy', ctxt=['ww'], returns=['*v'])
    def spectroscopy(self, c, ctxt):
        """Runs a Spectroscopy Sequence"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SPECTROSCOPYPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            # Add Microwave Pulse
            p.experiment_turn_off_deconvolution(uCh(i))
            p.experiment_set_anritsu(uCh(i), q['uwfrq'], q['sppow'])
            p.sram_iq_delay         (uCh(i), q['uwofs'] + 50)
            p.sram_iq_envelope      (uCh(i), [1.0]*int(q['splen']), 0.0, 0.0)
                        
            # Build Sequence
            mpSeq = SFT.rampPulse2(q['splen'], q['mptop'], q['mptal'], q['mpamp'])
            time = q['splen'] + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, time=time)

        # Run experiment and return result
        data = yield self.run_qubits_separate(c, p, pars['Stats'])
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
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            # Calculate frequency and measure pulse amplitude
            bias = q['fbias']
            fcal = q['frcal']
            mcal = q['mpcal']
            
            frq = ((float(fcal[0])*bias*bias + float(fcal[1])*bias + float(fcal[2]))*1000.0)**0.25 + q['dfreq']
            mpa =                              float(mcal[0])*bias + float(mcal[1])
            
            # Add Microwave Pulse
            p.experiment_turn_off_deconvolution(uCh(i))
            p.experiment_set_anritsu(uCh(i), frq, q['sppow'])
            p.sram_iq_delay         (uCh(i), q['uwofs'] + 50)
            p.sram_iq_envelope      (uCh(i), [1.0]*int(q['splen']), 0.0, 0.0)
            
            # Build Sequence
            mpSeq = SFT.rampPulse2(q['splen'], q['mptop'], q['mptal'], mpa)
            time = q['splen'] + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, time=time)

            frqs.append(frq)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(frqs+data)
        

    @inlineCallbacks
    def tophatExp(self, c, ctxt, runFunc):
        """Runs a single TopHat pulse sequence"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, TOPHATPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            p.experiment_set_anritsu(uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            
            uwSeq = SFT.zPulse(0, q['plen1'], q['pamp1'], q['sbfrq'])
            
            mpSeq = SFT.rampPulse2(q['plen1'] + q['mpdel'], q['mptop'], q['mptal'], q['mpamp'])
            
            time = q['plen1'] + q['mpdel'] + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time=time)

        # Run experiment and return result
        data = yield runFunc(c, p, pars['Stats'])
        returnValue(data)

    @setting(40, 'TopHat Pulse', ctxt=['ww'], returns=['*v'])
    def tophat(self, c, ctxt):
        """Runs a Sequence with a single TopHat pulse (good for Rabis)"""
        return self.tophatExp(c, ctxt, self.run_qubits)
        

    @setting(41, 'TopHat Pulse Separate', ctxt=['ww'], returns=['*v'])
    def tophatsep(self, c, ctxt):
        """Runs a Sequence with a single TopHat pulse (good for Rabis) and returns probabilities for each qubit separately"""
        return self.tophatExp(c, ctxt, self.run_qubits_separate)
        

    @setting(50, 'Slepian Pulse', ctxt=['ww'], returns=['*v'])
    def slepian(self, c, ctxt):
        """Runs a Sequence with a single Slepian pulse (good for Power Rabis, T1, 2 Qubit Coupling, etc.)"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SLEPIANPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]

            p.experiment_set_anritsu(uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            
            uwSeq = SFT.gaussian_envelope(0, q['plen1']/2, q['pamp1'], q['sbfrq'], q['pphs1'])
            
            mpSeq = SFT.rampPulse2(q['plen1']/2 + q['mpdel'], q['mptop'], q['mptal'], q['mpamp'])
            
            time = q['plen1']/2 + q['mpdel'] + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(51, 'Slepian Pulse SS', ctxt=['ww'], returns=['*v'])
    def slepianss(self, c, ctxt):
        """Runs a Sequence with a single Slepian pulse (good for Power Rabis, T1, 2 Qubit Coupling, etc.)"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SLEPIANPARS)

        p2 = self.client.sequences_fft.packet(context = c.ID)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]

            p.experiment_set_anritsu(uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])

            p2.add_iq_channel(uCh(i))

            p2.add_gaussian(0, q['plen1']/2, q['pamp1'], q['sbfrq'], q['pphs1'])

            p2.add_analog_channel(mCh(i))

            p2.add_ramp_pulse_2(q['plen1']/2 + q['mpdel'], q['mptop'], q['mptal'], q['mpamp'])

        p2.upload(PADDING)

        yield p2.send()

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(60, 'Two Slepian Pulses', ctxt=['ww'], returns=['*v'])
    def twoslepian(self, c, ctxt):
        """Runs a Sequence with two Slepian pulses"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, TWOSLEPIANPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            p.experiment_set_anritsu(uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            
            uwSeq = SFT.gaussian(0, q['plen1']/2.0, q['pamp1'], q['sbfrq'], q['pphs1'])
            
            ptime2 = q['plen1']/2 + q['pdel2'] + q['plen2']/2
            uwSeq += SFT.gaussian(ptime2, q['plen2']/2.0, q['pamp2'], q['pfrq2'] - q['pfrq1'] + q['sbfrq'], q['pphs2'])
            
            mptime = ptime2 + q['plen2']/2 + q['mpdel']
            mpSeq = SFT.rampPulse2(mptime, q['mptop'], q['mptal'], q['mpamp'])
            
            time = mptime + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(61, 'Three Slepian Pulses', ctxt=['ww'], returns=['*v'])
    def threeslepian(self, c, ctxt):
        """Runs a Sequence with three Slepian pulses"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, THREESLEPIANPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            p.experiment_set_anritsu(uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            
            uwSeq = SFT.gaussian(0, q['plen1']/2.0, q['pamp1'], q['sbfrq'], q['pphs1'])
            
            ptime2 = q['plen1']/2 + q['pdel2'] + q['plen2']/2
            uwSeq += SFT.gaussian(ptime2, q['plen2']/2.0, q['pamp2'], q['pfrq2'] - q['pfrq1'] + q['sbfrq'], q['pphs2'])
            
            ptime3 = ptime2 + q['plen2']/2 + q['pdel3'] + q['plen3']/2
            uwSeq += SFT.gaussian(ptime3, q['plen3']/2.0, q['pamp3'], q['pfrq3'] - q['pfrq1'] + q['sbfrq'], q['pphs3'])
            
            mptime = ptime3 + q['plen3']/2 + q['mpdel']
            mpSeq = SFT.rampPulse2(mptime, q['mptop'], q['mptal'], q['mpamp'])
            
            time = mptime + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(70, 'Slepian-Z-Slepian Pulses', ctxt=['ww'], returns=['*v'])
    def slepzslep(self, c, ctxt):
        """Runs a Sequence with a Slepian pulse followed by a Z pulse followed by another Slepian pulse"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SLEPZSLEPPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]

            p.experiment_set_anritsu (uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            p.experiment_set_settling(mCh(i), q['srate'], q['sampl'])
            
            uwSeq = SFT.gaussian(0, q['plen1']/2.0, q['pamp1'], q['sbfrq'], q['pphs1'])
            
            ptime2 = q['plen1']/2 + q['zdel1'] + q['zlen1'] + q['pdel2'] + q['plen2']/2
            uwSeq += SFT.gaussian(ptime2, q['plen2']/2.0, q['pamp2'], q['pfrq2'] - q['pfrq1'] + q['sbfrq'], q['pphs2'])
            
            ztime = q['plen1']/2 + q['zdel1']
            mpSeq = SFT.zPulse(ztime, q['zlen1'], q['zamp1'], overshoot=q['zovs1'])
            
            mptime = ptime2 + q['plen2']/2 + q['mpdel']
            mpSeq += SFT.rampPulse2(mptime, q['mptop'], q['mptal'], q['mpamp'])
            
            time = mptime + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(71, 'Slepian-Z-Z-Slepian Pulses', ctxt=['ww'], returns=['*v'])
    def slepzzslep(self, c, ctxt):
        """Runs a Sequence with a Slepian pulse followed by two Z pulses followed by another Slepian pulse"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, ctxt, GLOBALPARS, SLEPZZSLEPPARS)

        # Build SRAM
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            p.experiment_set_anritsu (uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            p.experiment_set_settling(mCh(i), q['srate'], q['sampl'])

            uwSeq = SFT.gaussian(0, q['plen1']/2.0, q['pamp1'], q['sbfrq'], q['pphs1'])
            
            ptime2 = q['plen1']/2 + q['zdel1'] + q['zlen1'] + q['zdel2'] + q['zlen2'] + q['pdel2'] + q['plen2']/2
            uwSeq += SFT.gaussian(ptime2, q['plen2']/2.0, q['pamp2'], q['pfrq2'] - q['pfrq1'] + q['sbfrq'], q['pphs2'])
            
            ztime = q['plen1']/2 + q['zdel1']
            mpSeq = SFT.zPulse(ztime, q['zlen1'], q['zamp1'], overshoot=q['zovs1'])


            ztim2 = ztime + q['zlen1'] + q['zdel2']
            mpSeq += SFT.zPulse(ztim2, q['zlen2'], q['zamp2'], overshoot=q['zovs2'])
            
            mptime = ptime2 + q['plen2']/2 + q['mpdel']
            mpSeq += SFT.rampPulse2(mptime, q['mptop'], q['mptal'], q['mpamp'])
            
            time = mptime + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time)

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
        for i, qname in enumerate(qubits):
            q = pars[qname]
            
            mpSeq = SFT.rampPulse2(q['plen1']/2 + q['mpdel'], q['mptop'], q['mptal'], q['mpamp'])
            
            time = q['plen1']/2 + q['mpdel'] + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, time=time)            

        # Reinitialize for second data point
        p = yield self.reinit_qubits(c, p, qubits)

        # Build SRAM for |1>-state
        for i, qname in enumerate(qubits):
            q = pars[qname]

            p.experiment_set_anritsu(uCh(i), q['pfrq1'] - q['sbfrq'], q['uwpow'])
            
            uwSeq = SFT.gaussian_envelope(0, q['plen1']/2, q['pamp1'], q['sbfrq'], q['pphs1'])
            
            mpSeq = SFT.rampPulse2(q['plen1']/2 + q['mpdel'], q['mptop'], q['mptal'], q['mpamp'])
            
            time = q['plen1']/2 + q['mpdel'] + q['mptop'] + q['mptal']
            self.uploadSram(p, q, i, mpSeq, uwSeq, time)

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
    from labrad import util
    util.runServer(__server__)
