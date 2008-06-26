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
from labrad.units  import Unit, mV, us

from copy import deepcopy

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

UL = Unit('')

DEFAULT_CONFIG = {'Reset Bias Low'         : -1000.0*mV,
                  'Reset Bias High'        : -1000.0*mV,
                  'Reset Settling Time'    :     7.0*us,
                  'Reset Cycles'           :     0.0*UL,
                  
                  'Operating Bias'         :   100.0*mV,
                  'Operating Settling Time':    50.0*us,

                  'Readout Bias'           :     0.0*mV,
                  'Readout Settling Time'  :     7.0*us,

                  'Squid Ramp Delay'       :     0.0*us,
                  'Squid Zero Bias'        :     0.0*mV,
                  'Squid Ramp Start'       :     0.0*mV,
                  'Squid Ramp End'         :  1000.0*mV,
                  'Squid Ramp Time'        :    25.0*us,

                  '|1>-State Cutoff'       :    15.0*us}

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
        
class ContextNotFoundError(T.Error):
    code = 6
    def __init__(self, context):
        self.msg="Context (%d, %d) not found" % context


def getCMD(DAC, value):
    return DAC*0x10000 + 0x60000 + (int((value+2500.0)*65535.0/5000.0) & 0x0FFFF)


class QubitBiasServer(LabradServer):
    name = 'Qubit Bias'
    sendTracebacks = False

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
            p.cd(['', 'Servers', 'Qubit Bias'], True)
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
        p.cd(['', 'Servers', 'Qubit Bias', name])
        p.dir()
        ans = yield p.send()
        qubits = ans.dir[0]
        
        c['Config'] = name
        c['Overrides'] = {}
        self.Configs[name] = {}
        p = self.client.registry.packet()
        for qubit in qubits:
            p.cd(['', 'Servers', 'Qubit Bias', name, qubit])
            p.dir(key=qubit)
            self.Configs[name][qubit]={}
        ans = yield p.send()
        
        p = self.client.registry.packet()
        for qubit in qubits:
            p.cd(['', 'Servers', 'Qubit Bias', name, qubit])
            values = ans[qubit][1]
            for value in values:
                p.get(value, key=(qubit, value))
        ans = yield p.send()
        for key in ans.settings.keys():
            if isinstance(key, tuple):
                self.Configs[name][key[0]][key[1]]=ans[key]
        returnValue(self.Configs[name].keys())

    @setting(4, 'Config Save', name=['s'])
    def config_save(self, c, name=None):
        """Save a configuration to the Registry"""
        cfgname, config = self.getConfig(c, name)
        p = self.client.registry.packet()
        for qname, qvals in config.items():
            p.cd(['', 'Servers', 'Qubit Bias', cfgname, qname], True)
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


    @setting(100, 'Initialize Qubits', operatingbias=['v[mV]', '*(s{Qubit}v[mV])', ], returns=['*(sv[mV]): Operating Biases by Qubit'])
    def initialize(self, c, operatingbias=None):
        """Send qubit initialization commands to Qubit Server"""
        qubits = yield self.getQubits(c)

        # Get Operating Bias Overrides
        opbiases = {}
        if operatingbias is not None:
            if isinstance(operatingbias, list):
                opbiases = dict(operatingbias.aslist)
            else:
                opbiases[qubits[0][0]] = operatingbias
        
        # Generate Memory Building Blocks
        initreset = []
        dac1s = []
        reset1 = []
        reset2 = []
        maxresetsettling = 7
        maxbiassettling = 7
        maxcount = 0
        setop = []
        for qid, qubitinfo in enumerate(qubits):
            qname, qubit = qubitinfo
            # Set Flux to Reset Low and Squid to Zero
            initreset.extend([(('Flux',  qid+1), getCMD(1, qubit['Reset Bias Low' ].inUnitsOf('mV'))),
                              (('Squid', qid+1), getCMD(1, qubit['Squid Zero Bias'].inUnitsOf('mV')))])
            # Set Bias DACs to DAC 1
            dac1s.extend([(('Flux', qid+1), 0x50001), (('Squid', qid+1), 0x50001)])
            # Set Flux to Reset Low
            reset1.append((('Flux',  qid+1), getCMD(1, qubit['Reset Bias Low'].inUnitsOf('mV'))))
            # Set Flux to Reset High
            reset2.append((('Flux',  qid+1), getCMD(1, qubit['Reset Bias High'].inUnitsOf('mV'))))
            # Set Flux to Operating Bias
            if qname in opbiases:
                opbias = opbiases[qname]
            else:
                opbias = qubit['Operating Bias']
            setop.append((('Flux', qid+1), getCMD(1, opbias.inUnitsOf('mV'))))
            # Find maximum number of reset cycles
            if qubit['Reset Cycles'] > maxcount:
                maxcount = qubit['Reset Cycles']
            # Find maximum Reset Settling Time
            settle = float(qubit['Reset Settling Time'].inUnitsOf('us'));
            if settle > maxresetsettling:
                maxresetsettling = settle
            # Find maximum Bias Settling Time
            settle = float(qubit['Operating Settling Time'].inUnitsOf('us'));
            if settle > maxbiassettling:
                maxbiassettling = settle

        # Upload Memory Commands
        p = self.client.qubits.packet(context=c.ID)
        p.memory_bias_commands(initreset, 7.0*us)
        p.memory_bias_commands(dac1s, maxresetsettling*us)
        for a in range(maxcount):
            p.memory_bias_commands(reset2, maxresetsettling*us)
            p.memory_bias_commands(reset1, maxresetsettling*us)
        p.memory_bias_commands(setop, maxbiassettling*us)
        yield p.send()

        ret = dict([(qubit[0], qubit[1]['Operating Bias']) for qubit in qubits])
        for name, value in opbiases.items():
            if name in ret:
                ret[name] = value
        returnValue(ret.items())


    @setting(101, 'Readout Qubits', returns=['*(sv[us]): |1>-State Cutoffs by Qubit (negative if |1> switches BEFORE |0>)'])
    def readout(self, c):
        """Send qubit readout commands to Qubit Server"""
        qubits = yield self.getQubits(c)

        # Build TODO List based on requested Squid Ramp Delays
        setreadout = []
        setzero    = []
        maxsettling = 7
        todo = {}
        for qid, qubitinfo in enumerate(qubits):
            qname, qubit = qubitinfo
            delay = float(qubit['Squid Ramp Delay'].inUnitsOf('us'))
            if delay in todo:
                todo[delay].append((qid, qubit))
            else:
                todo[delay]=[(qid, qubit)]
            # Build Readout Bias Commands
            setreadout.append( (('Flux', qid+1), getCMD(1, qubit['Readout Bias'].inUnitsOf('mV'))))
            setzero.extend   ([(('Flux', qid+1), getCMD(1, 0)), (('Squid', qid+1), getCMD(1, 0))])
            # Find maximum Readout Settling Time
            settle = float(qubit['Readout Settling Time'].inUnitsOf('us'));
            if settle > maxsettling:
                maxsettling = settle

        # Build and send memory commands
        p = self.client.qubits.packet(context=c.ID)
        p.memory_bias_commands(setreadout, maxsettling*us)
        curdelay = 0.0;
        for key in sorted(todo.keys()):
            # Add any necessary delays (initial delays get stripped)
            if (curdelay>0) and (key>curdelay):
                p.memory_delay(key-curdelay)
            curdelay = key
            # Add squid ramp
            srstart   = []
            dac1slow  = []
            timers    = []
            srend     = []
            srzeros   = []
            dac1fast  = []
            maxramp   = 7
            for qid, qubit in todo[key]:
                # Set Squid Bias to Ramp Start
                srstart.append((('Squid', qid+1), getCMD(1, qubit['Squid Ramp Start'].inUnitsOf('mV'))))
                # Set Bias DACs to DAC 1 slow
                dac1slow.append((('Squid', qid+1), 0x50002))
                # Start/Stop Timer
                timers.append(qid+1)
                # Set Squid Bias to Ramp End
                srend.append((('Squid', qid+1), getCMD(1, qubit['Squid Ramp End'].inUnitsOf('mV'))))
                # Find maximum Readout Settling Time
                ramp = float(qubit['Squid Ramp Time'].inUnitsOf('us'));
                if ramp > maxramp:
                    maxramp = ramp
                # Set Flux to Reset Low and Squid to Zero
                srzeros.append((('Squid', qid+1), getCMD(1, qubit['Squid Zero Bias'].inUnitsOf('mV'))))
                # Set Bias DACs to DAC fast
                dac1fast.append((('Squid', qid+1), 0x50001))

            # Send Memory Commands
            p.memory_bias_commands(srstart,   7.0*us)
            p.memory_bias_commands(dac1slow,  5.0*us)
            p.memory_start_timer  (timers)
            p.memory_bias_commands(srend, maxramp*us)
            p.memory_bias_commands(srzeros,   7.0*us)
            p.memory_stop_timer   (timers)
            p.memory_bias_commands(dac1fast,  5.0*us)
            curdelay += 24.08 + maxramp
        p.memory_bias_commands(setzero, maxsettling*us)
        yield p.send()
        
        returnValue([(qubit[0], qubit[1]['|1>-State Cutoff']) for qubit in qubits])

__server__ = QubitBiasServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
