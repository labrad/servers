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

PARAMETERS = [("uWave Offset",        "ns" ),
              
               "Pi Amplitude",
              ("Pi Phase",            "deg"),
              ("Pi Length",           "ns" ),

              ("Coupling Time",       "ns" ),

              ("Bell Length",         "ns" ),
              
               "Amplitude",
              ("Phase",               "deg"),
              
               "Amplitude'",          
              ("Phase'",              "deg"),

              ("Measure Offset",      "ns" ),

              ("Bias Shift",          "mV" ),

              ("Measure Delay",       "ns" ),
               "Measure Amplitude",
              ("Measure Top Length",  "ns" ),
              ("Measure Tail Length", "ns" )]


class NeedTwoQubitsError(T.Error):
    """Must select a two qubit experiment"""
    code = 1


class VoBIServer(LabradServer):
    name = 'Bell Violation'

                  
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
                result[key]=ans[key]
        returnValue(result)


    @inlineCallbacks
    def run(self, c, ops, stats):
        qubits = yield self.getQubits(c)
        if len(qubits)!=2:
            raise NeedTwoQubitsError()
        
        pars   = yield self.readParameters(c, qubits, PARAMETERS)
        
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
            qsw = qs.duplicate_context(c.ID, context=ctxt)

            # Setup Registry Server
            rsw = rg.duplicate_context(c.ID, context=ctxt)

            # Wait for Servers to complete Request
            yield qsw
            yield rsw

            # Setup Qubit Bias Server
            p = qb.packet(context=ctxt)
            p.duplicate_context(c.ID)

            # Reset Qubits
            p.initialize_qubits()
            yield p.send()

            # Add SRAM Sequence
            p = qs.packet(context=ctxt)
            for qid, qname in enumerate(qubits):
                # Initial Delay
                p.sram_iq_delay        (('uWaves',  qid+1), pars[(qname, "uWave Offset" )] + 50.0*ns)
                # Pi Pulse
                p.sram_iq_slepian      (('uWaves',  qid+1), pars[(qname, "Pi Amplitude" )],
                                                            pars[(qname, "Pi Length"    )], 150.0*MHz,
                                                            pars[(qname, "Pi Phase"     )])
                # Coupling Delay
                p.sram_iq_delay        (('uWaves',  qid+1), pars[(qname, "Coupling Time")])
                # Bell Pulses
                # A, B
                if op==0:
                    p.sram_iq_slepian  (('uWaves',  qid+1), pars[(qname, "Amplitude"    )],
                                                            pars[(qname, "Bell Length"  )], 150.0*MHz,
                                                            pars[(qname, "Phase"        )])
                # A', B or B', A
                if op in [1,2]:
                  if ((op+qid) % 2)==0:
                    p.sram_iq_slepian  (('uWaves',  qid+1), pars[(qname, "Amplitude"    )],
                                                            pars[(qname, "Bell Length"  )], 150.0*MHz,
                                                            pars[(qname, "Phase"        )])
                  else:
                    p.sram_iq_slepian  (('uWaves',  qid+1), pars[(qname, "Amplitude'"   )],
                                                            pars[(qname, "Bell Length"  )], 150.0*MHz,
                                                            pars[(qname, "Phase'"       )])
                # A', B'
                if op==3:
                    p.sram_iq_slepian  (('uWaves',  qid+1), pars[(qname, "Amplitude'"   )],
                                                            pars[(qname, "Bell Length"  )], 150.0*MHz,
                                                            pars[(qname, "Phase'"       )])
                # A'
                if (op==4) and (qid==0):
                    p.sram_iq_slepian  (('uWaves',  qid+1), pars[(qname, "Amplitude'"   )],
                                                            pars[(qname, "Bell Length"  )], 150.0*MHz,
                                                            pars[(qname, "Phase'"       )])
                # B
                if (op==5) and (qid==1):
                    p.sram_iq_slepian  (('uWaves',  qid+1), pars[(qname, "Amplitude"    )],
                                                            pars[(qname, "Bell Length"  )], 150.0*MHz,
                                                            pars[(qname, "Phase"        )])

                # Measure Delay
                measofs = 50 + int(pars[(qname, "Measure Offset")]) + int(pars[(qname, "Measure Delay")])
                p.sram_analog_data (('Measure', qid+1), [pars[(qname, "Bias Shift")]]*measofs)
                # Measure Pulse
                meastop  = int  (pars[(qname, "Measure Top Length" )])
                meastail = int  (pars[(qname, "Measure Tail Length")])
                measamp  = float(pars[(qname, "Measure Amplitude"  )])/1000.0
                measpuls = [measamp]*meastop + [(meastail - t - 1)*measamp/meastail for t in range(meastail)]
                p.sram_analog_data (('Measure', qid+1), measpuls)
            yield p.send()

            # Readout Qubits
            cutoffs.append((yield qb.readout_qubits(context=ctxt)))

            # Request Data Run
            waits.append(qs.run(stats, context=ctxt))

        results =  []
        for wait, coinfos in zip(waits, cutoffs):
            switches = yield wait
            cutoffs = [float(coinfo[1].inUnitsOf('us')) for coinfo in coinfos]
            neg_cutoffs = [cutoff<0       for cutoff in cutoffs]
            cutoffs     = [abs(cutoff)*25 for cutoff in cutoffs]
            switches = [[int((s<cutoff) ^ neg_cutoff) for s in ss] for ss, neg_cutoff, cutoff in zip(switches, neg_cutoffs, cutoffs)]
            states = [s1+s2*2 for s1, s2 in zip(switches[0], switches[1])]
            states = [float(states.count(s))/float(len(states)) for s in range(4)]
            results.append(states)

        returnValue(results)


    @setting(100, 'Run Single', stats=['w'], returns=['*v'])
    def run_single(self, c, stats):
        """Runs Sequence for A, B only"""
        probs = yield self.run(c, 1, stats)
        returnValue(probs[0][1:])


    @setting(101, 'Run CHSH', stats=['w'], returns=['(*2v, *v, v)'])
    def run_chsh(self, c, stats):
        """Runs CHSH S Measurement"""
        probs = yield self.run(c, 4, stats)
        Es = [p[0] - p[1] - p[2] + p[3] for p in probs]
        S = Es[0] + Es[1] - Es[2] + Es[3]
        probs = [p[1:] for p in probs]
        returnValue((probs, Es, S))


    @setting(102, 'Run Korotkov', stats=['w'], returns=['(*2v, *v, v)'])
    def run_koko(self, c, stats):
        """Runs Korotkov T Measurement"""
        probs = yield self.run(c, 6, stats)
        Rs = [p[0] for p in probs]
        Rs[4] += probs[4][2]
        Rs[5] += probs[5][1]
        T = Rs[0] + Rs[1] - Rs[2] + Rs[3] - Rs[4] - Rs[5]
        probs = [p[1:] for p in probs]
        returnValue((probs, Rs, T))

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
