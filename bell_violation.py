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
from labrad.units  import Unit, mV, ns, deg, MHz

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

GLOBALPARS = [ "Stats" ];

QUBITPARAMETERS = [("Microwave Offset",          "ns" ),
                   ("Resonance Frequency",       "GHz"),
                   ("Sideband Frequency",        "GHz"),
                   ("Carrier Power",             "dBm"), 
              
                   ("Measure Offset",            "ns" ),

                   ("Measure Pulse Delay",       "ns" ),
                    "Measure Pulse Amplitude",
                   ("Measure Pulse Top Length",  "ns" ),
                   ("Measure Pulse Tail Length", "ns" )]

BELLPARAMETERS  = [ "Pi Pulse Amplitude",
                   ("Pi Pulse Phase",            "rad"),
                   ("Pi Pulse Length",           "ns" ),

                   ("Coupling Time",             "ns" ),

                   ("Bell Pulse Length",         "ns" ),
              
                    "Bell Pulse Amplitude",
                   ("Bell Pulse Phase",          "rad"),
              
                    "Bell Pulse Amplitude'",          
                   ("Bell Pulse Phase'",         "rad"),

                    "Operating Bias Shift"             ]


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
                if isinstance(parameter, tuple):
                    name, units = parameter
                    # Load setting with units
                    p.get(name, 'v[%s]' % units, key=(qubit, name))
                else:
                    # Load setting without units
                    p.get(parameter, key=(qubit, parameter))
            # Change into bell directory
            p.cd('Bell Violation', key=False)
            for parameter in bellpars:
                if isinstance(parameter, tuple):
                    name, units = parameter
                    # Load setting with units
                    p.get(name, 'v[%s]' % units, key=(qubit, name))
                else:
                    # Load setting without units
                    p.get(parameter, key=(qubit, parameter))
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
        qubits = yield self.getQubits(cctxt)
        if len(qubits)!=2:
            raise NeedTwoQubitsError()
        
        pars   = yield self.readParameters(c, GLOBALPARS, qubits, QUBITPARAMETERS, BELLPARAMETERS)
        
        cxn = self.client
        if 'Contexts' not in c:
            c['Contexts'] = (cxn.context(), cxn.context(), cxn.context(),
                             cxn.context(), cxn.context(), cxn.context())
            
        qs = cxn.qubits
        rg = cxn.registry
        qb = cxn.qubit_bias
        
        waits = []
        cutoffs = []
        for op in range(ops):
            ctxt = c['Contexts'][op]
            # Setup Qubit Server
            qsw = qs.duplicate_context(cctxt, context=ctxt)

            # Setup Registry Server
            rsw = rg.duplicate_context(c.ID, context=ctxt)

            # Wait for Servers to complete Request
            yield qsw
            yield rsw

            # Reset Qubits
            yield qb.initialize_qubits(context=ctxt)

            # Add SRAM Sequence
            p = qs.packet(context=ctxt)
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
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase"         )])
                # A', B or B', A
                if op in [1,2]:
                  if ((op+qid) % 2)==0:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude"     )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase"         )])
                  else:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude'"    )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase'"        )])
                # A', B'
                if op==3:
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude'"    )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase'"        )])
                # A'
                if (op==4) and (qid==0):
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude'"    )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase'"        )])
                # B
                if (op==5) and (qid==1):
                    p.sram_iq_slepian   (('uWaves',  qid+1), pars[(qname, "Bell Pulse Amplitude"     )],
                                                             pars[(qname, "Bell Pulse Length"        )],
                                                       float(pars[(qname, 'Sideband Frequency'       )])*1000.0,
                                                             pars[(qname, "Bell Pulse Phase"         )])

                # Measure Delay
                measofs = 50 +                           int(pars[(qname, "Measure Offset"           )]) + \
                                                         int(pars[(qname, "Pi Pulse Length"          )]) + \
                                                         int(pars[(qname, "Coupling Time"            )]) + \
                                                         int(pars[(qname, "Bell Pulse Length"        )]) + \
                                                         int(pars[(qname, "Measure Pulse Delay"      )])
                p.sram_analog_data (('Measure', qid+1), [float(pars[(qname, "Operating Bias Shift")])]*measofs)

                # Measure Pulse
                meastop  = int  (pars[(qname, "Measure Pulse Top Length" )])
                meastail = int  (pars[(qname, "Measure Pulse Tail Length")])
                measamp  = float(pars[(qname, "Measure Pulse Amplitude"  )])/1000.0
                measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
                p.sram_analog_data  (('Measure', qid+1), measpuls)
                
            p.memory_call_sram()
            yield p.send()

            # Readout Qubits
            cutoffs.append((yield qb.readout_qubits(context=ctxt)))

            # Request Data Run
            waits.append(qs.run(pars["Stats"], context=ctxt))

        results =  []
        for wait, coinfos in zip(waits, cutoffs):
            switches = yield wait
            results.append(analyzeData(coinfos, switches))

        returnValue(results)


    @setting(100, 'Run Single', context=['ww'], returns=['*v'])
    def run_single(self, c, context):
        """Runs Sequence for A, B only"""
        probs = yield self.run(c, context, 1)
        returnValue(probs[0][1:])


    @setting(101, 'Run CHSH', context=['ww'], returns=['(*2v, *v, v)'])
    def run_chsh(self, c, context):
        """Runs CHSH S Measurement"""
        probs = yield self.run(c, context, 4)
        Es = [p[0] - p[1] - p[2] + p[3] for p in probs]
        S = Es[0] + Es[1] - Es[2] + Es[3]
        probs = [p[1:] for p in probs]
        returnValue((probs, Es, S))


    @setting(102, 'Run Korotkov', context=['ww'], returns=['(*2v, *v, v)'])
    def run_koko(self, c, context):
        """Runs Korotkov T Measurement"""
        probs = yield self.run(c, context, 6)
        Rs = [p[0] for p in probs]
        Rs[4] += probs[4][2]
        Rs[5] += probs[5][1]
        T = Rs[0] + Rs[1] - Rs[2] + Rs[3] - Rs[4] - Rs[5]
        probs = [p[1:] for p in probs]
        returnValue((probs, Rs, T))


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
