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
from labrad.units  import Unit, mV, ns, deg, rad, MHz, GHz

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

import numpy

dBm = Unit('dBm')

GLOBALPARS = [ "Stats", "Sequence" ];

QUBITPARAMETERS = [("Microwave Offset",          "Timing",        "Microwave Offset",    "ns",   50.0*ns ),
                   ("Resonance Frequency",       "Spectroscopy",  "Frequency",           "GHz",   6.5*GHz),
                   ("Sideband Frequency",        "Microwaves",    "Sideband Frequency",  "GHz",-150.0*MHz),
                   ("Carrier Power",             "Microwaves",    "Carrier Power",       "dBm",   2.7*dBm), 

                   ("Measure Offset",            "Timing",        "Measure Offset",      "ns",   50.0*ns ),
                   ("Measure Pulse Delay",       "Measure Pulse", "Delay",               "ns",    5.0*ns ),
                   ("Measure Pulse Amplitude",   "Measure Pulse", "Amplitude",           "mV",  500.0*mV ),
                   ("Measure Pulse Top Length",  "Measure Pulse", "Top Length",          "ns",    5.0*ns ),
                   ("Measure Pulse Tail Length", "Measure Pulse", "Tail Length",         "ns",   15.0*ns )]

BELLPARAMETERS  = [("Pi Pulse Amplitude",        "mV",  500.0*mV ),
                   ("Pi Pulse Phase",            "rad",   0.0*rad),
                   ("Pi Pulse Length",           "ns",   16.0*ns ),

                   ("Coupling Time",             "ns",   20.0*ns ),

                   ("Bell Pulse Length",         "ns",   10.0*ns ),
                   ("Bell Pulse Bias Shift",     "mV",    0.0*mV ),
                   ("Bell Pulse Frequency Shift","GHz",   0.0*GHz),

                   ("Bell Pulse Amplitude",      "mV",  100.0*mV ),
                   ("Bell Pulse Phase",          "rad",   0.0*rad),
              
                   ("Bell Pulse Amplitude'",     "mV",  200.0*mV ),   
                   ("Bell Pulse Phase'",         "rad",   0.0*rad),

                   ("Operating Bias Shift",      "mV",    0.0*mV )]


def analyzeData(cutoffs, data):
    nQubits = len(cutoffs)
    states = 2**len(cutoffs)
    data = data.T # indexed by [rep#, qubit#]
    total = data.shape[0]
    cutoffNums = numpy.array([c[1] for c in cutoffs])
    isOne = (data/25.0 > abs(cutoffNums)) ^ (cutoffNums < 0)
    state = sum(2**qid * isOne[:,qid] for qid in range(nQubits))
    counts = [sum(state==s) for s in range(states)]
    #total  = len(data[0])
    #for pid in range(total):
    #    n = 0
    #    for qid in range(len(data)):
    #        if (data[qid][pid]/25.0>abs(cutoffs[qid][1])) ^ (cutoffs[qid][1]<0):
    #            n+=2**qid
    #    counts[n]+=1.0
    return [c/float(total) for c in counts]


class NeedTwoQubitsError(T.Error):
    """Must select a two qubit experiment"""
    code = 1


class VoBIServer(LabradServer):
    name = 'Bell Violation'

                  
    def getQubits(self, cctxt):
        return self.client.qubits.experiment_involved_qubits(context=cctxt)


    @inlineCallbacks
    def readParameters(self, c, globalpars, qubits, qubitpars, bellpars):
        # Make a new packet for the registry
        p = self.client.registry.packet()
        # Copy current directory and overrides from client context
        p.duplicate_context(c.ID)
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
                name, path, key, units, default = parameter
                # Load setting with units
                p.cd(path, True, key=False)
                p.get(key, 'v[%s]' % units, True, default, key=(qubit, name))
                p.cd(1, key=False)
            # Change into bell directory
            p.cd('Bell Violation', True, key=False)
            for parameter in bellpars:
                name, units, default = parameter
                # Load setting with units
                p.get(name, 'v[%s]' % units, True, default, key=(qubit, name))
            # Change back to root directory
            p.cd(2, key=False)
        # Get parameters
        ans = yield p.send()
        # Build and return parameter dictionary
        result = {}
        for key in ans.settings.keys():
            if isinstance(key, tuple) or isinstance(key, str):
                result[key]=ans[key]
        returnValue(result)


    @inlineCallbacks
    def run(self, c, cctxt, ops):
        # Get list of qubits and make sure it contains exactly 2 qubits
        qubits = yield self.getQubits(cctxt)
        if len(qubits)!=2:
            raise NeedTwoQubitsError()

        # Read experimental parameters
        pars   = yield self.readParameters(c, GLOBALPARS, qubits, QUBITPARAMETERS, BELLPARAMETERS)

        # Grab reference to servers
        qs = self.client.qubits
        qb = self.client.qubit_bias

        # Initialize Qubit Server
        qs.duplicate_context(cctxt, context=c.ID)

        # Run all measurement combinations as one sequence
        for o in range(ops):
            if ops==1:
                op = pars["Sequence"]
            else:
                op = o

            # Reset Qubits
            yield qb.initialize_qubits(context=c.ID)

            # Add SRAM sequence
            p = qs.packet(context=c.ID)
            for qid, qname in enumerate(qubits):
                # Add a trigger
                p.sram_trigger_pulse    (('Trigger', qid+1), 20*ns)
                
                # Setup Anritsu
                p.experiment_set_anritsu(('uWaves',  qid+1), pars[(qname, 'Resonance Frequency'      )]- \
                                                             pars[(qname, 'Sideband Frequency'       )],
                                                             pars[(qname, 'Carrier Power'            )])
                
                # Initial Delay
                p.sram_iq_delay         (('uWaves',  qid+1), pars[(qname, 'Microwave Offset'         )]+50*ns)

                # Pi Pulse
                p.sram_iq_slepian       (('uWaves',  qid+1), pars[(qname, 'Pi Pulse Amplitude'       )],
                                                             pars[(qname, 'Pi Pulse Length'          )],
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, 'Pi Pulse Phase'           )])
                # Coupling Delay
                p.sram_iq_delay         (('uWaves',  qid+1), pars[(qname, 'Coupling Time'            )])
                # Bell Pulses
                # A, B
                if op==0:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude"     )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )]+
                                                             pars[(qname, 'Bell Pulse Frequency Shift')])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase"         )])
                # A', B or B', A
                if op in [1,2]:
                  if ((op+qid) % 2)==0:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude"     )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )]+
                                                             pars[(qname, 'Bell Pulse Frequency Shift')])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase"         )])
                  else:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude'"    )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )]+
                                                             pars[(qname, 'Bell Pulse Frequency Shift')])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase'"        )])
                # A', B'
                if op==3:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude'"    )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )]+
                                                             pars[(qname, 'Bell Pulse Frequency Shift')])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase'"        )])
                # A'
                if (op==4) and (qid==0):
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude'"    )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )]+
                                                             pars[(qname, 'Bell Pulse Frequency Shift')])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase'"        )])
                # B
                if (op==5) and (qid==1):
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude"     )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )]+
                                                             pars[(qname, 'Bell Pulse Frequency Shift')])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase"         )])

                # Add measure delay, allowing for negative numbers
                totmeasdel = 50 +                        int(pars[(qname, "Measure Offset"           )]) + \
                                                         int(pars[(qname, "Pi Pulse Length"          )]) + \
                                                         int(pars[(qname, "Coupling Time"            )]) + \
                                                         int(pars[(qname, "Bell Pulse Length"        )]) + \
                                                         int(pars[(qname, "Measure Pulse Delay"      )])
                    
                # Wait until Coupling is done
                measofs = max(min(totmeasdel, 50 +       int(pars[(qname, "Measure Offset"           )]) + \
                                                         int(pars[(qname, "Pi Pulse Length"          )]) + \
                                                         int(pars[(qname, "Coupling Time"            )])), 0)
                if measofs>0:
                    p.sram_analog_data (('Measure', qid+1), [float(pars[(qname, "Operating Bias Shift"   )])]*measofs)

                # Bell and Measure Delay
                measofs = max(totmeasdel-measofs, 0)
                if measofs>0:
                    p.sram_analog_data (('Measure', qid+1), [float(pars[(qname, "Bell Pulse Bias Shift"  )])]*measofs)

                if (op<4) or ((op==4) and (qid==0)) or ((op==5) and (qid==1)):
                    # Measure Pulse
                    meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
                    meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
                    measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
                    measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
                    p.sram_analog_data  (('Measure', qid+1), measpuls)

            # Insert SRAM call into memory
            p.memory_call_sram()
            yield p.send()

            # Readout Qubits
            cutoffs = yield qb.readout_qubits(context=c.ID)

        # Run experiment
        data = yield qs.run(pars["Stats"], context=c.ID)

        # Deinterlace data
        data = data.asarray.reshape(2, pars["Stats"], ops)

        # Turn switching data into probabilities
        results = [analyzeData(cutoffs, data[:,:,op]) for op in range(ops)]

        returnValue(results)


    @setting(100, 'Run Single', context=['ww'], returns=['*v'])
    def run_single(self, c, context):
        """Runs Sequence for A, B only"""
        probs = yield self.run(c, context, 1)
        returnValue(probs[0][1:])


    @setting(200, 'Run CHSH', context=['ww'], returns=['*v'])
    def run_chsh(self, c, context):
        """Runs CHSH S Measurement and returns 17 values:

        P(|10>), P(|01>), P(|11>) for ab, a'b, ab', a'b'

        E(ab), E(a'b), E(ab'), E(a'b')

        S
        """
        probs = yield self.run(c, context, 4)
        Es = [p[0] - p[1] - p[2] + p[3] for p in probs]
        S = Es[0] + Es[1] - Es[2] + Es[3]
        probs = [p for ps in probs for p in ps[1:]]
        returnValue(probs + Es + [S])


    @setting(201, 'Run CHSH (S only)', context=['ww'], returns=['*v'])
    def run_chsh_s_only(self, c, context):
        """Runs CHSH S Measurement and returns only S"""
        probs = yield self.run(c, context, 4)
        Es = [p[0] - p[1] - p[2] + p[3] for p in probs]
        S = Es[0] + Es[1] - Es[2] + Es[3]
        returnValue([S])


    @setting(300, 'Run Korotkov', context=['ww'], returns=['*v'])
    def run_koko(self, c, context):
        """Runs Korotkov T Measurement and returns 25 values:

        P(|10>), P(|01>), P(|11>) for ab, a'b, ab', a'b', a', b

        R(ab), R(a'b), R(ab'), R(a'b'), R(a'), R(b)

        T
        """
        probs = yield self.run(c, context, 6)
        Rs = [p[0] for p in probs]
        Rs[4] += probs[4][2]
        Rs[5] += probs[5][1]
        T = Rs[0] + Rs[1] - Rs[2] + Rs[3] - Rs[4] - Rs[5]
        probs = [p for ps in probs for p in ps[1:]]
        returnValue(probs + Rs + [T])


    @setting(301, 'Run Korotkov (T only)', context=['ww'], returns=['*v'])
    def run_koko_t_only(self, c, context):
        """Runs Korotkov T Measurement and returns only T"""
        probs = yield self.run(c, context, 6)
        Rs = [p[0] for p in probs]
        Rs[4] += probs[4][2]
        Rs[5] += probs[5][1]
        T = Rs[0] + Rs[1] - Rs[2] + Rs[3] - Rs[4] - Rs[5]
        returnValue([T])


    @setting(100000, 'Kill')
    def kill(self, c, context):
        reactor.callLater(1, reactor.stop);

__server__ = VoBIServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
