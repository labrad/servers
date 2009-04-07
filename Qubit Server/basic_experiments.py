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
name = Basic Experiments
version = 1.1
description = Standard qubit experiments (T1, Rabi, etc.)

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
## END NODE INFO
"""

from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import Unit, mV, ns, deg, MHz, V, GHz, rad

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from math import log
import numpy

GLOBALPARS = [('Stats', 'w', 300L),
              ('Setup', 's', '')]

dBm = Unit('dBm')
SCURVEPARS =       [('Measure Offset',            'Timing',        'Measure Offset',      'v[ns]',   50.0*ns ),
                    ('Measure Pulse Amplitude',   'Measure Pulse', 'Amplitude',           'v[mV]',  500.0*mV ),
                    ('Measure Pulse Top Length',  'Measure Pulse', 'Top Length',          'v[ns]',    5.0*ns ),
                    ('Measure Pulse Tail Length', 'Measure Pulse', 'Tail Length',         'v[ns]',   15.0*ns )]

SPECTROSCOPYPARS = SCURVEPARS + \
                   [('Microwave Offset',          'Timing',        'Microwave Offset',    'v[ns]',   50.0*ns ),
                    ('Spectroscopy Pulse Length', 'Spectroscopy',  'Pulse Length',        'v[ns]',   2000*ns ),
                    ('Resonance Frequency',       'Spectroscopy',  'Frequency',           'v[GHz]',   6.5*GHz),
                    ('Spectroscopy Power',        'Spectroscopy',  'Power',               'v[dBm]', -30.0*dBm)]

SPEC2DPARS =       SCURVEPARS + \
                   [('Microwave Offset',          'Timing',        'Microwave Offset',    'v[ns]',   50.0*ns ),
                    ('Spectroscopy Pulse Length', 'Spectroscopy',  'Pulse Length',        'v[ns]',   2000*ns ),
                    ('Operating Bias',            'Bias',          'Operating Bias',      'v[V]',    0.05*V  ),
                    ('Frequency Shift',           'Spectroscopy',  'dFrequency',          'v[GHz]',   6.5*GHz),
                    ('Measure Calibration',       'Measure Pulse', 'Calibration',         'vv',     (1.0,1.0)),
                    ('Frequency Calibration',     'Spectroscopy',  'Calibration',         'vvv',(1.0,1.0,1.0)),
                    ('Spectroscopy Power',        'Spectroscopy',  'Power',               'v[dBm]', -30.0*dBm)]

TOPHATPARS =       SCURVEPARS + \
                   [('Microwave Offset',          'Timing',        'Microwave Offset',    'v[ns]',   50.0*ns ),
                    ('Carrier Power',             'Microwaves',    'Carrier Power',       'v[dBm]',   2.7*dBm), 
                    ('Sideband Frequency',        'Microwaves',    'Sideband Frequency',  'v[GHz]',-150.0*MHz),
                    ('Microwave Pulse Length',    'Pulse 1',       'Length',              'v[ns]',   16.0*ns ),
                    ('Microwave Pulse Amplitude', 'Pulse 1',       'Amplitude',           'v[mV]',  100.0*mV ),
                    ('Resonance Frequency',       'Pulse 1',       'Frequency',           'v[GHz]',   6.5*GHz),
                    ('Measure Pulse Delay',       'Measure Pulse', 'Delay',               'v[ns]',    5.0*ns )]

SLEPIANPARS =      TOPHATPARS + \
                   [('Microwave Pulse Phase',     'Pulse 1',       'Phase',               'v[rad]',   0.0*rad)]

TWOSLEPIANPARS =   SLEPIANPARS + \
                   [('Second Pulse Length',       'Pulse 2',       'Length',              'v[ns]',   16.0*ns ),
                    ('Second Pulse Delay',        'Pulse 2',       'Delay',               'v[ns]',   10.0*ns ),
                    ('Second Pulse Amplitude',    'Pulse 2',       'Amplitude',           'v[mV]',  100.0*mV ),
                    ('Second Pulse Phase',        'Pulse 2',       'Phase',               'v[rad]', 180.0*rad),
                    ('Second Frequency',          'Pulse 2',       'Frequency',           'v[GHz]', 200.0*MHz)]



class NeedOneQubitError(T.Error):
    """Must select a single qubit experiment"""
    code = 1

class NeedTwoQubitsError(T.Error):
    """Must select a two qubit experiment"""
    code = 2


def applyCutoffs(cutoffs, data):
    """Helper function that applies cutoffs to switching data.
    
    Takes a list of cutoffs and a 2D-array of switching data
    indexed by qubit #, rep # (this is the form in which switching
    data is returned by the ghz dac server) and returns a 2D boolean
    array which tells the qubit state |0> or |1>.  Note that the
    returned data array is transposed, so that it is indexed by
    rep #, then qubit #.  This is merely for convenience in applying
    numpy operators, which match the last index.  In addition, 
    returns the total number of reps in data.
    """
    if not ininstance(data, numpy.ndarray):
        data = data.asarray
    data = data.asarray.T # indexed by [rep#, qubit#]
    total = data.shape[0]
    cutoffs = numpy.array(cutoffs)
    isOne = (data/25.0 > abs(cutoffs)) ^ (cutoffs < 0)
    return total, isOne

def analyzeData(cutoffs, data, asPercent=True, drop0=True):
    """Find probabilities for combined qubit states.
    
    Takes a list of cutoffs and a 2D-array of switching data
    and returns a list of the probabilities for qubit states
    |0..00>, |0..01>, |0..10> etc.
    
    The probability can be returned as a percentage (0-100)
    or a true probability (0-1).  In addition, the |0..00> state
    probability can be dropped if desired, since all probabilities
    must sum to 1, so no information is lost by dropping it.
    """
    total, isOne = applyCutoffs(cutoffs, data)
    nQubits = len(cutoffs)
    state = sum(2**i * isOne[:,i] for i in range(nQubits))
    counts = [sum(state==s) for s in range(2**nQubits)]
    multiplier = 100.0 if asPercent else 1
    return [c*multiplier/float(total) for c in counts[drop0:]]

def analyzeDataSeparate(cutoffs, data, asPercent=True):
    """Find switching probabilities for individual qubits.
    
    Takes a list of cutoffs and returns a list of the
    switching probabilities of the individual qubits.
    The probability can be returned as a percentage (0-100)
    or a true probability (0-1).
    """
    total, isOne = applyCutoffs(cutoffs, data)
    counts = sum(isOne)
    multiplier = 100.0 if asPercent else 1
    return [c*multiplier/float(total) for c in counts]


class BEServer(LabradServer):
    """Provides basic experiments for bringing up a qubit."""
    name = 'Basic Experiments'

    @inlineCallbacks
    def readParameters(self, c, globalpars=[], qubits=[], parameters=[]):
        """Read parameters from the registry for each qubit.
        
        Any parameters that do not yet exist will be created
        and set to the default values specified above.
        """
        p = self.client.registry.packet(context=c.ID) # start a new packet
        # Load global parameters
        for name, typ, default in globalpars:
            p.get(name, typ, True, default, key=name)
        # Load qubit-specific parameters
        for qubit in qubits:
            p.cd(qubit, True) # change into qubit directory
            for name, path, key, typ, default in parameters: # load parameters
                if isinstance(path, str):
                    path = [path]
                p.cd(path, True, key=False)
                p.get(key, typ, True, default, key=(qubit, name))
                p.cd(len(path), key=False)
            p.cd(1) # change back to root directory
        ans = yield p.send()
        # build and return parameter dictionary
        pars = {}
        for name, typ, default in globalpars:
            pars[name] = ans[name]
        for qubit in qubits:
            pars[qubit] = {}
            for name, typ, default in parameters:
                pars[qubit][name] = ans[qubit, name]
        returnValue(pars)

    @inlineCallbacks              
    def startExperiment(self, c, setup):
        """Get a list of qubits used in the current experiment."""
        p = self.client.qubits.packet(context=c.ID)
        p.experiment_new(setup)
        p.experiment_involved_devices('qubit', key='qubits')
        ans = yield p.send()
        returnValue(ans['qubits'])


    @setting(1, 'Squid Step', ctxt='ww', returns='*2v')
    def squid_steps(self, c, ctxt):
        """Runs a Squid Steps Sequence for a single Readout Bias"""
        # Make sure we have a single qubit experiment selected
        cxn = self.client
        globs = yield self.readParameters(c, GLOBALPARS)
        setup = globs['setup']
        stats = globs['stats']
        
        qubits = yield self.startExperiments(c, setup)
        if len(qubits) != 1:
            raise NeedOneQubitError()
        # Get name of qubit
        qubit = qubits[0]
        
        # Set up qubit reset for negative reset
        p = cxn.registry.packet(context=c.ID)
        p.cd      ([qubit, 'Bias'])
        p.override('Operating Bias', -2.5*V)
        p.cd      (2)
        ans = yield p.send()
        
        # Add sequence for negative reset
        p = cxn.qubit_bias.packet(context=c.ID)
        p.initialize_qubits()
        p.readout_qubits()
        yield p.send()

        # Set up qubit reset for positive reset
        p = cxn.registry.packet(context=c.ID)
        p.cd      ([qubit, 'Bias'])
        p.override('Operating Bias', 2.5*V)
        p.cd      (2)
        yield p.send()

        # Add sequence for positive reset
        p = cxn.qubit_bias.packet(context=c.ID)
        p.initialize_qubits()
        p.readout_qubits()
        yield p.send()

        # Run qubit
        data = yield cxn.qubits.run(stats, context=c.ID)

        # Process switching data
        data = data.asarray[0].reshape(stats, 2) / 25.0

        returnValue(data)


    @inlineCallbacks
    def run_step_edge(self, c):
        cxn = self.client
        
        # fetch stats but don't wait
        globs = yield self.readParameters(c, GLOBALPARS)
        setup = globs['setup']
        stats = globs['stats']

        # build sequence
        yield self.startExperiment(c, setup)
        yield cxn.qubit_bias.initialize_qubits(context=c.ID) # initialize
        yield cxn.qubits.memory_call_sram(context=c.ID) # run SRAM to sync boards
        cutoffs = yield cxn.qubit_bias.readout_qubits(context=c.ID) # readout

        # run experiment after waiting for stats fetch
        data = yield cxn.qubits.run(stats, context=c.ID)
        returnValue((cutoffs, data))


    @setting(10, 'Step Edge (Switching Data)', ctxt='ww', returns='*2v')
    def step_edge_switch(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        raw switching data as a scatter plot like Squid Step does"""
        cutoffs, data = yield self.run_step_edge(c) # take data

        # Convert to us
        # TODO: use numpy arrays here
        dat = []
        for pid in range(len(data[0])):
            d = []
            for i in range(len(data)):
                d.append(data[i][pid]/25.0)
            dat.append(d)

        returnValue(dat)


    @setting(11, 'Step Edge (Probability)', ctxt='ww', returns='*v')
    def step_edge_prob(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        tunneling probabilities"""
        cutoffs, data = yield self.run_step_edge(c) # take data
        returnValue(analyzeData(cutoffs, data)) # convert to probs


    @setting(12, 'Step Edge (Probability, Separate)', ctxt='ww', returns='*v')
    def step_edge_prob_sep(self, c, ctxt):
        """Runs a Step Edge Sequence for a single Operating Bias and returns the
        tunneling probabilities"""
        cutoffs, data = yield self.run_step_edge(c) # take data
        returnValue(analyzeDataSeparate(cutoffs, data)) # convert to probs


    @inlineCallbacks
    def init_qubits(self, c, globalpars, qubitpars):
        """Create sequence up to calling SRAM block."""
        globs = yield self.readParameters(c, globalpars)
        qubits = yield self.startExperiment(c, globs['setup'])
        pars = yield self.readParameters(c, globalpars, qubits, qubitpars)
        
        yield self.client.qubit_bias.initialize_qubits(context=c.ID) # reset qubits

        # add trigger to start of SRAM block
        p = self.client.qubits.packet(context=c.ID)
        for n in qubits:
            p.sram_trigger_pulse((q, 'Trigger'), 20*ns)
        returnValue((qubits, pars, p))

    @inlineCallbacks
    def reinit_qubits(self, c, p, qubits):
        """Finish SRAM, reset qubits, and start aonther run."""
        p.memory_call_sram() # finish SRAM
        yield p.send()
        
        # Readout qubits
        p = self.client.qubit_bias.packet(context=c.ID)
        p.readout_qubits()

        # Initialize qubits
        p.initialize_qubits()
        yield p.send()

        # begin next SRAM block with a trigger
        p = self.client.qubits.packet(context=c.ID)
        for q in qubits:
            p.sram_trigger_pulse((q, 'Trigger'), 20*ns)
        returnValue(p)                      

    @inlineCallbacks
    def run_qubits(self, c, p, stats):
        """Finish SRAM, readout qubits, and run."""
        p.memory_call_sram()
        yield p.send()
        
        cutoffs = yield self.client.qubit_bias.readout_qubits(context=c.ID)
        data = yield self.client.qubits.run(stats, context=c.ID)
        returnValue(analyzeData(cutoffs, data))


    @inlineCallbacks
    def run_qubits_separate(self, c, p, stats, n=1):
        """Finish SRAM, readout qubits and run."""
        p.memory_call_sram()
        yield p.send()
        
        cutoffs = yield self.client.qubit_bias.readout_qubits(context=c.ID)
        data = yield self.client.qubits.run(stats, context=c.ID)
        data = data.asarray

        if n == 1:
            returnValue(analyzeDataSeparate(cutoffs, data))
        
        # deinterlace data and turn it into probabilities
        data = data.reshape(-1, stats, n)
        results = [analyzeDataSeparate(cutoffs, data[:,:,i]) for i in range(n)]
        returnValue(results)        


    @setting(20, 'S-Curve', ctxt='ww', returns='*v')
    def s_curve(self, c, ctxt):
        """Runs an S-Curve Sequence and returns P|10..>, P|01...>, ..., P|11...>"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, SCURVEPARS)

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Add Measure Delay
            p.sram_analog_delay((n, 'Measure'), 50*ns + q['Measure Offset'])
            
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude']) / 1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)


    @setting(21, 'S-Curve Separate', ctxt='ww', returns='*v')
    def s_curve_sep(self, c, ctxt):
        """Runs an S-Curve Sequence and returns P|1xx...>, P|x1x...>, P|xx1...>, ..."""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, SCURVEPARS)

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Add Measure Delay
            p.sram_analog_delay((n, 'Measure'), 50*ns + q['Measure Offset'])
            
            # Measure PulseanalyzeDataSeparate
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude'])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits_separate(c, p, pars['Stats'])
        returnValue(data)
  

    @setting(30, 'Spectroscopy', ctxt='ww', returns='*v')
    def spectroscopy(self, c, ctxt):
        """Runs a Spectroscopy Sequence"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, SPECTROSCOPYPARS)

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Add Microwave Pulse
            p.experiment_turn_off_deconvolution((n, 'uWaves'))
            p.experiment_set_anritsu((n, 'uWaves'), q['Resonance Frequency'],
                                                    q['Spectroscopy Power' ])
            p.sram_iq_delay         ((n, 'uWaves'), q['Microwave Offset'] + 50*ns)
            p.sram_iq_envelope      ((n, 'uWaves'), [1.0]*int(q['Spectroscopy Pulse Length']), 0.0, 0.0)
            
            # Add Measure Delay
            p.sram_analog_delay((n, 'Measure'), 50*ns + q['Measure Offset'] + \
                                                        q['Spectroscopy Pulse Length'])
            
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude']) / 1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)


    @setting(31, '2D Spectroscopy', ctxt='ww', returns='*v')
    def spec2D(self, c, ctxt):
        """Runs a Spectroscopy Sequence using the Operating Bias to calculate the
        Measure Pulse Amplitude and Resonance Frequency. Returns the frequency of
        each data point."""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, SPEC2DPARS)

        frqs = []

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Calculate frequency and measure pulse amplitude
            bias = float(q['Operating Bias'       ])
            fcal =       q['Frequency Calibration']
            mcal =       q['Measure Calibration'  ]
            
            frq =  (float(fcal[0])*bias*bias + float(fcal[1])*bias + float(fcal[2]))**4 + float(q['Frequency Shift'])
            mpa =                              float(mcal[0])*bias + float(mcal[1])
            
            # Add Microwave Pulse
            p.experiment_turn_off_deconvolution((n, 'uWaves'))
            p.experiment_set_anritsu((n, 'uWaves'), frq,
                                                    q['Spectroscopy Power'])
            p.sram_iq_delay         ((n, 'uWaves'), q['Microwave Offset'] + 50*ns)
            p.sram_iq_envelope      ((n, 'uWaves'), [1.0]*int(q['Spectroscopy Pulse Length']), 0.0, 0.0)
            
            # Add Measure Delay
            p.sram_analog_delay ((n, 'Measure'), 50*ns + q['Measure Offset'] + \
                                                         q['Spectroscopy Pulse Length'])
            
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = mpa
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

            frqs.append(frq)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(frqs + data)
        

    @setting(40, 'TopHat Pulse', ctxt='ww', returns='*v')
    def tophat(self, c, ctxt):
        """Runs a Sequence with a single TopHat pulse (good for Rabis)"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, TOPHATPARS)

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Add Microwave Pulse
            p.experiment_set_anritsu((n, 'uWaves'), q['Resonance Frequency'] - \
                                                    q['Sideband Frequency'],
                                                    q['Carrier Power'])
            p.sram_iq_delay         ((n, 'uWaves'), q['Microwave Offset'] + 50*ns)
            pulse = [float(q['Microwave Pulse Amplitude'])/1000.0]*int(q['Microwave Pulse Length'])
            p.sram_iq_envelope      ((n, 'uWaves'), pulse, float(q['Sideband Frequency'])*1000.0, 0.0)
            
            # Add Measure Delay
            p.sram_analog_delay ((n, 'Measure'), 50*ns + q['Measure Offset'] + \
                                                         q['Microwave Pulse Length'] + \
                                                         q['Measure Pulse Delay'])
            
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude'])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(50, 'Slepian Pulse', ctxt='ww', returns='*v')
    def slepian(self, c, ctxt):
        """Runs a Sequence with a single Slepian pulse (good for Power Rabis, T1, 2 Qubit Coupling, etc.)"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, SLEPIANPARS)

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Add Microwave Pulse
            p.experiment_set_anritsu((n, 'uWaves'), q['Resonance Frequency'] - \
                                                    q['Sideband Frequency'],
                                                    q['Carrier Power'])
            p.sram_iq_delay         ((n, 'uWaves'), q['Microwave Offset'] + 50*ns)
            p.sram_iq_slepian       ((n, 'uWaves'), float(q['Microwave Pulse Amplitude']) / 1000.0,
                                                    q['Microwave Pulse Length'],
                                                    float(q['Sideband Frequency'])*1000.0,
                                                    q['Microwave Pulse Phase'])
            # Add Measure Delay
            p.sram_analog_delay     ((n, 'Measure'), q['Measure Offset'        ] + \
                                                     q['Microwave Pulse Length'] + \
                                                     q['Measure Pulse Delay'   ] + 50*ns)
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude'])/1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)
        

    @setting(60, 'Two Slepian Pulses', ctxt='ww', returns='*v')
    def twoslepian(self, c, ctxt):
        """Runs a Sequence with two Slepian pulses"""
        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, TWOSLEPIANPARS)

        # Build SRAM
        for n in qubits:
            q = pars[n]
            # Add Microwave Pulse
            p.experiment_set_anritsu((n, 'uWaves'), q['Resonance Frequency'      ]- \
                                                    q['Sideband Frequency'       ],
                                                    q['Carrier Power'            ])
            p.sram_iq_delay         ((n, 'uWaves'), q['Microwave Offset'         ] + 50*ns)
            p.sram_iq_slepian       ((n, 'uWaves'), float(q['Microwave Pulse Amplitude']) / 1000.0,
                                                    q['Microwave Pulse Length'   ],
                                                    float(q['Sideband Frequency'       ]) * 1000.0,
                                                    q['Microwave Pulse Phase'    ])
            p.sram_iq_delay         ((n, 'uWaves'), q['Second Pulse Delay'       ])
            p.sram_iq_slepian       ((n, 'uWaves'), float(q['Second Pulse Amplitude'   ]) / 1000.0,
                                                          q['Second Pulse Length'      ],
                                                   (float(q['Second Frequency'         ]) - \
                                                    float(q['Resonance Frequency'      ]) + \
                                                    float(q['Sideband Frequency'       ])) * 1000.0,
                                                          q['Second Pulse Phase'       ])
            # Add Measure Delay
            p.sram_analog_delay     ((n, 'Measure'), q['Measure Offset'        ] + \
                                                     q['Microwave Pulse Length'] + \
                                                     q['Second Pulse Delay'    ] + \
                                                     q['Second Pulse Length'   ] + \
                                                     q['Measure Pulse Delay'   ] + 50*ns)
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude']) / 1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

        # Run experiment and return result
        data = yield self.run_qubits(c, p, pars['Stats'])
        returnValue(data)


    @setting(100, 'Visibility', ctxt='ww', returns='*v')
    def visibility(self, c, ctxt):
        """Runs a Sequence with and without a single Slepian pulse and returns Pw(|1>), Pw/o(|1>) and Pw-Pw/o for each qubit"""

        data = []

        # Initialize experiment
        qubits, pars, p = yield self.init_qubits(c, GLOBALPARS, SLEPIANPARS)

        # Build SRAM for |0>-state
        for n in qubits:
            q = pars[n]
            # Add Measure Delay
            p.sram_analog_delay((n, 'Measure'), q['Measure Offset'        ] + \
                                                q['Microwave Pulse Length'] + \
                                                q['Measure Pulse Delay'   ] + 50*ns)
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude']) / 1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)
            

        # Reinitialize for second data point
        p = yield self.reinit_qubits(c, p, qubits)

        # Build SRAM for |1>-state
        for n in qubits:
            q = pars[n]
            # Add Microwave Pulse
            p.experiment_set_anritsu((n, 'uWaves'), q['Resonance Frequency'] - \
                                                    q['Sideband Frequency' ],
                                                    q['Carrier Power'      ])
            p.sram_iq_delay  ((n, 'uWaves'), q['Microwave Offset'] + 50*ns)
            p.sram_iq_slepian((n, 'uWaves'), float(q['Microwave Pulse Amplitude']) / 1000.0,
                                                   q['Microwave Pulse Length'],
                                             float(q['Sideband Frequency']) * 1000.0,
                                                   q['Microwave Pulse Phase'])
            # Add Measure Delay
            p.sram_analog_delay((n, 'Measure'), q['Measure Offset'        ] + \
                                                q['Microwave Pulse Length'] + \
                                                q['Measure Pulse Delay'   ] + 50*ns)
            # Measure Pulse
            meastop  = int(q['Measure Pulse Top Length'])
            meastail = int(q['Measure Pulse Tail Length'])
            measamp  = float(q['Measure Pulse Amplitude']) / 1000.0
            measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
            p.sram_analog_data((n, 'Measure'), measpuls)

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
