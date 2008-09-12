from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import Unit, mV, ns, deg, MHz

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from numpy import arange, array, mean, shape
from scipy.interpolate.interpolate import interp1d
from time import time

GLOBALPARS = [ "Stats" ];

PARAMETERS = [ "Chirp End DAC",
               "Chirp Start DAC",
              ("Chirp Time",                "ns"),
              ("Chirp Wait",                "ns"),
              ("Gate Open Offset",          "ns"),
              ("Gate Closed Offset",        "ns"),
               "Attenuator Device",
               "Attenuation"]

class ResetServer(LabradServer):
    name = 'uWave Reset'

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
            p.cd(qubit)
            for parameter in qubitpars:
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
            if key!="cd":
                result[key]=ans[key]
        returnValue(result)

    @setting(20, 'Test Reset', ctxt=['ww'])
    def test(self, c, ctxt):
        cxn = self.client
        qs = cxn.qubits
        rg = cxn.registry
        qb = cxn.qubit_bias
        dv = cxn.data_vault
        #xy = cxn.xy_attenuator_server

        qubits = yield self.getQubits(ctxt)
        pars = yield self.readParameters(c, GLOBALPARS, qubits, PARAMETERS)

        yield qs.duplicate_context(ctxt, context=c.ID)

        # reset qubits
        yield qb.initialize_qubits(context=c.ID)

        # set up SRAM data
        p = qs.packet(context=c.ID)
        setupPackets = []
        setupState = []
        
        for qid, qname in enumerate(qubits):
            # turn off deconvolution for all qubits
            p.experiment_turn_off_deconvolution(('Chirp', qid+1))
            
            # create setupPacket for xy attenuator
            dev = pars[qname, 'Attenuator Device']
            atten = pars[qname, 'Attenuation']
            recs = (('Select Device', dev),
                    ('Total Atten', atten))
            state = 'Attenuator Device: %s=%s' % (dev, atten)
            setupPackets.append((c.ID, 'XY Attenuator Server', recs))
            setupState.append(state)
            
            # get params
            start = float(pars[(qname, 'Chirp Start DAC')])
            end = float(pars[(qname, 'Chirp End DAC')])
            duration = int(pars[(qname, 'Chirp Time')])
            wait = int(pars[(qname, 'Chirp Wait')])
            openoff = int(pars[(qname, 'Gate Open Offset')])
            closedoff = int(pars[(qname, 'Gate Closed Offset')])

            # build the chirp
            timeArray = array(range(duration))
            dacArray = ((end-start)/duration)*timeArray + start
            p.sram_analog_data(('Chirp', qid+1), [start]*wait)
            p.sram_analog_data(('Chirp', qid+1), dacArray)
            p.sram_analog_data(('Chirp', qid+1), [end]*wait)

            # set up gate
            p.sram_trigger_delay(('Gate', qid+1), wait + openoff)
            p.sram_trigger_pulse(('Gate', qid+1), duration + closedoff - openoff)

            # trigger
            p.sram_trigger_delay(('Trigger', qid+1), wait - 40)
            p.sram_trigger_pulse(('Trigger', qid+1), 20)

        p.memory_call_sram()
        yield p.send()

        # measure
        cutoffs = yield qb.readout_qubits(context=c.ID)

        # run everything
##        # pretty print without hint
##        pp0 = yield self.client.manager.pretty_print(pars['Stats'], tuple(setupPackets), setupState)
##        print 'without hint:', pp0
##        # pretty print with hint
##        pp1 = yield self.client.manager.pretty_print(pars['Stats'], tuple(setupPackets), setupState, tag=qs.run.accepts)
##        print 'with hint:', pp1
##        # compare pretty-printed versions
##        print 'Same with or without hint?', pp0 == pp1
        data = yield qs.run_without_anritsu(pars['Stats'], setupPackets, setupState, context=c.ID)

        returnValue((cutoffs, data))

    @setting(30, 'Test Reset Probabilities', ctxt=['ww'], returns=['*v'])
    def testProb(self, c, ctxt):
        cutoffs, data = yield self.test(c, ctxt)
        data = array(data)
        
        # return whether the qubit was reset
        probs = [0.0]*len(cutoffs)
        for qid, cutoff in enumerate(cutoffs):
            probs[qid] = mean((data[qid,:]/25.0 > abs(cutoff[1])) ^ (cutoff[1]<0))*100.0
        returnValue(probs)

__server__ = ResetServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)

