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

UL = Unit('')

DEFAULT_CONFIG = {"uWave Offset"           :     0.0*ns,
                  
                  "Pi Amplitude"           :     1.0*UL,
                  "Pi Phase"               :     0.0*deg,
                  "Pi Length"              :    12.0*ns,

                  "Coupling Time"          :    20.0*ns,

                  "Bell Length"            :     5.0*ns,
                  
                  "Amplitude"              :     0.0*UL,
                  "Phase"                  :     0.0*deg,
                  
                  "Amplitude'"             :     0.5*UL,
                  "Phase'"                 :   180.0*deg,

                  "Measure Offset"         :     0.0*ns,

                  "Bias Shift"             :     0.0*mV, 

                  "Measure Delay"          :    14.0*ns,
                  "Measure Amplitude"      :   250.0*UL,
                  "Measure Top Length"     :     5.0*ns,
                  "Measure Tail Length"    :    50.0*ns}

class NoConfigurationError(T.Error):
    """No configuration selected"""
    code = 1

class ConfigNotFoundError(T.Error):
    code = 2
    def __init__(self, name):
        self.msg="Configuration '%s' not found" % name
        
class QubitNotFoundError(T.Error):
    code = 3
    def __init__(self, config, qubit):
        self.msg="Qubit '%s' not found in configuration '%s'" % (qubit, config)

class NoQubitError(T.Error):
    """No qubit selected"""
    code = 4
        
class ParameterNotFoundError(T.Error):
    code = 5
    def __init__(self, config, qubit, name):
        self.msg="Qubit '%s' in configuration '%s' does not have a parameter '%s'" % (qubit, config, name)

class NeedTwoQubitsError(T.Error):
    """Must select a two qubit experiment"""
    code = 6


class VoBIServer(LabradServer):
    name = 'Bell Violation'

    def getConfig(self, c, name = None):
        if name is None:
            if 'Config' not in c:
                raise NoConfigurationError();
            name = c['Config']
        if not (name in self.Configs):
            raise ConfigNotFoundError(name)
        return name, self.Configs[name]

    def getQubit(self, c, name = None):
        if name is None:
            if 'Qubit' not in c:
                raise NoQubitError();
            name = c['Qubit']
        cfgname, config = self.getConfig(c)
        if not (name in config):
            raise QubitNotFoundError(cfgname, name)
        return cfgname, name, config[name]

    def getParameter(self, c, name):
        cfgname, qname, qubit = self.getQubit(c, qubit)
        if not (name in qubit):
            raise ParameterNotFoundError(cfgname, qname, name)
        return qubit[name]

    @inlineCallbacks
    def getQubits(self, c):
        qubits = yield self.client.qubits.experiment_involved_qubits(context=c.ID)
        returnValue ([tuple(self.getQubit(c, qubit)[1:]) for qubit in qubits])
                  

    def initServer(self):
        self.Configs = {}


    @setting(10000, 'Duplicate Context', prototype=['(ww)'])
    def dupe_ctxt(self, c, prototype):
        if prototype[0]==0:
            prototype = (c.ID[0], prototype[1])
        if prototype not in self.prot.queues:
            raise ContextNotFoundError(prototype)
        newc = deepcopy(self.prot.queues[prototype].ctxtData)
        for key in c.keys():
            if key not in newc:
                del c[key]
        c.update(newc)


    @setting(1, 'Config List', loaded=['b'], returns=['*s'])
    def config_list(self, c, loaded=False):
        """List all available (b=False) or loaded (b=True) configurations"""
        if not loaded:
            p = self.client.registry.packet()
            p.cd(['', 'Servers', 'Bell Violation'], True)
            p.dir()
            ans = yield p.send()
            configs = ans.dir[0]
        else:
            configs = self.Configs.keys()
        returnValue(configs)

    @setting(2, 'Config New', name=['s'])
    def config_new(self, c, name):
        """Create a new configuration"""
        self.Configs[name] = {}
        c['Config'] = name
        c['Overrides'] = {}

    @setting(3, 'Config Load', name=['s'], returns=['*s'])
    def config_load(self, c, name):
        """Load a stored configuration from the Registry"""
        p = self.client.registry.packet()
        p.cd(['', 'Servers', 'Bell Violation', name])
        p.dir()
        ans = yield p.send()
        qubits = ans.dir[0]
        
        c['Config'] = name
        c['Overrides'] = {}
        self.Configs[name] = {}
        p = self.client.registry.packet()
        for qubit in qubits:
            p.cd(['', 'Servers', 'Bell Violation', name, qubit])
            p.dir(key=qubit)
            self.Configs[name][qubit]={}
        ans = yield p.send()
        
        p = self.client.registry.packet()
        for qubit in qubits:
            p.cd(['', 'Servers', 'Bell Violation', name, qubit])
            values = ans[qubit][1]
            for value in values:
                p.get(value, key=(qubit, value))
        ans = yield p.send()
        for key in ans.settings.keys():
            if isinstance(key, tuple):
                self.Configs[name][key[0]][key[1]]=ans[key]
        returnValue(self.Configs[name].keys())

    @setting(4, 'Config Save', name=['', 's'])
    def config_save(self, c, name=None):
        """Save a configuration to the Registry"""
        cfgname, config = self.getConfig(c, name)
        p = self.client.registry.packet()
        for qname, qvals in config.items():
            p.cd(['', 'Servers', 'Bell Violation', cfgname, qname], True)
            for vname, vval in qvals.items():
                p.set(vname, vval)
        yield p.send()

    @setting(5, 'Config Select', name=['s'])
    def config_select(self, c, name):
        """Select active configuration for this context"""
        self.getConfig(c, name)
        c['Config'] = name
        c['Overrides'] = {}


    @setting(10, 'Qubit List', returns=['*s'])
    def qubit_list(self, c):
        """List the qubits in the current configuration"""
        return self.getConfig(c).keys()[1]

    @setting(11, 'Qubit New', name=['s'])
    def qubit_new(self, c, name):
        """Adds a new qubit to the current configuration"""
        config = self.getConfig(c)[1]
        config[name]=DEFAULT_CONFIG
        c['Qubit']=name

    @setting(12, 'Qubit Select', name=['s'])
    def qubit_select(self, c, name):
        """Selects the current qubit"""
        self.getQubit(c, name)
        c['Qubit']=name
    

    @setting(20, 'Parameter List', returns=['*s'])
    def parameter_list(self, c):
        """List all standard parameters"""
        return sorted(DEFAULT_CONFIG.keys())
        
    @setting(21, 'Parameter Set', name=['s'], value=['v'])
    def parameter_set(self, c, name, value):
        """Sets a parameter on the current qubit"""
        self.getQubit(c)[2][name] = value
        
    @setting(22, 'Parameter Get', name=['s'], returns=['v'])
    def parameter_get(self, c, name):
        """Gets a parameter of the current qubit"""
        return self.getParameter(c, name)
        
    @setting(23, 'Parameter Get All', returns=['*(svs): Name, Value, Units'])
    def parameter_get_all(self, c):
        """Get all parameters of the current qubit"""        
        return sorted((vname, float(vval), vval.units) for vname, vval in self.getQubit(c)[2].items())

    @setting(25, 'Parameter Send To Data Vault', qubits=['', 's', '*s'])
    def parameters_save(self, c, qubits=None):
        """Store qubit parameters in the Data Vault"""
        if isinstance(qubits, list):
            qubits = [self.getQubit(c, qubit)[1:] for qubit in qubits]
        else:
            qubits = [self.getQubit(c, qubits)[1:]]
        p = self.client.data_vault.packet(context=c.ID)
        for qname, qubit in qubits:
            for key, value in qubit.items():
                p.add_parameter(qname+' - '+key, value)
        yield p.send()
        

    @setting(30, 'Parameter Set Override', name=['s'], value=['v'])
    def override_set(self, c, name, value):
        """Sets a parameter override for the current context on the current qubit"""
        cname, qname, qubit = self.getQubit(c)
        if qname not in c['Overrides']:
            c['Overrides'][qname] = {}
        c['Overrides'][qname][name] = value

    @setting(31, 'Parameter Clear Override', name=['s'])
    def override_clear(self, c, name):
        """Clears a parameter override for the current context on the current qubit"""
        cname, qname, qubit = self.getQubit(c)
        if qname in c['Overrides']:
            if name in c['Overrides'][qname]:
                del c['Overrides'][qname][name]

    @setting(32, 'Parameter Clear All Overrides')
    def override_clear_all(self, c):
        """Clears all parameter overrides for the current context on the current qubit"""
        c['Overrides'] = {}


    def getPar(self, c, qubits, qubitid, parameter, units=None):
        qname, qinfo = qubits[qubitid]
        result = qinfo[parameter]
        if qname in c['Overrides']:
            if parameter in c['Overrides'][qname]:
                result = c['Overrides'][qname][parameter]
        if units is not None:
            result = float(result.inUnitsOf(units))
        return result
        

    @inlineCallbacks
    def run(self, c, ops, stats):
        qubits = yield self.getQubits(c)
        if len(qubits)!=2:
            raise NeedTwoQubitsError()            
        
        cxn = self.client
        if 'Contexts' not in c:
            c['Contexts'] = (cxn.context(), cxn.context(), cxn.context(),
                             cxn.context(), cxn.context(), cxn.context())
        qb = cxn.qubit_bias
        qs = cxn.qubits
        waits = []
        cutoffs = []
        for op in range(ops):
            ctxt = c['Contexts'][op]
            # Setup Qubit Server
            yield qs.duplicate_context(c.ID, context=ctxt)

            # Setup Qubit Bias Server
            p = qb.packet(context=ctxt)
            p.duplicate_context(c.ID)

            # Reset Qubits
            p.initialize_qubits()
            yield p.send()

            # Add SRAM Sequence
            p = qs.packet(context=ctxt)
            for qid in range(2):
                # Initial Delay
                p.sram_iq_delay        (('uWaves',  qid+1), 50.0*ns + self.getPar(c, qubits, qid, "uWave Offset"))
                # Pi Pulse
                p.sram_iq_slepian      (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Pi Amplitude"),
                                                            self.getPar(c, qubits, qid, "Pi Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Pi Phase"))
                # Coupling Delay
                p.sram_iq_delay        (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Coupling Time"))
                # Bell Pulses
                # A, B
                if op==0:
                    p.sram_iq_slepian  (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Amplitude"),
                                                            self.getPar(c, qubits, qid, "Bell Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Phase"))
                # A', B or B', A
                if op in [1,2]:
                  if ((op+qid) % 2)==0:
                    p.sram_iq_slepian  (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Amplitude"),
                                                            self.getPar(c, qubits, qid, "Bell Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Phase"))
                  else:
                    p.sram_iq_slepian  (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Amplitude'"),
                                                            self.getPar(c, qubits, qid, "Bell Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Phase'"))
                # A', B'
                if op==3:
                    p.sram_iq_slepian  (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Amplitude'"),
                                                            self.getPar(c, qubits, qid, "Bell Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Phase'"))
                # A'
                if (op==4) and (qid==0):
                    p.sram_iq_slepian  (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Amplitude'"),
                                                            self.getPar(c, qubits, qid, "Bell Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Phase'"))
                # B
                if (op==5) and (qid==1):
                    p.sram_iq_slepian  (('uWaves',  qid+1), self.getPar(c, qubits, qid, "Amplitude"),
                                                            self.getPar(c, qubits, qid, "Bell Length"), 150.0*MHz,
                                                            self.getPar(c, qubits, qid, "Phase"))

                # Measure Delay
                measofs = 50 + int(self.getPar(c, qubits, qid, "Measure Offset", 'ns'))
                p.sram_analog_data (('Measure', qid+1), [self.getPar(c, qubits, qid, "Bias Shift")]*measofs)
                # Measure Pulse
                meastop  = int  (self.getPar(c, qubits, qid, "Measure Top Length",  'ns'))
                meastail = int  (self.getPar(c, qubits, qid, "Measure Tail Length", 'ns'))
                measamp  = float(self.getPar(c, qubits, qid, "Measure Amplitude"        ))/1000.0
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
        """Runs Experiment for A, B only"""
        probs = yield self.run(c, 1, stats)
        returnValue(probs[0])


    @setting(101, 'Run CHSH', stats=['w'], returns=['(*2v, *v, v)'])
    def run_chsh(self, c, stats):
        """Runs CHSH S Measurement"""
        probs = yield self.run(c, 4, stats)
        Es = [p[0] - p[1] - p[2] + p[3] for p in probs]
        S = Es[0] + Es[1] - Es[2] + Es[3]
        returnValue((probs, Es, S))


    @setting(102, 'Run Korotkov', stats=['w'], returns=['(*2v, *v, v)'])
    def run_koko(self, c, stats):
        """Runs Korotkov T Measurement"""
        probs = yield self.run(c, 6, stats)
        Rs = [p[0] for p in probs]
        Rs[4] += probs[4][2]
        Rs[5] += probs[5][1]
        T = Rs[0] + Rs[1] - Rs[2] + Rs[3] - Rs[4] - Rs[5]
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
