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

from labrad import types as T, util
from labrad.server import LabradServer, setting

from copy import deepcopy

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from datetime import datetime

import numpy

CHANNELS = ['ch1', 'ch2']


def getCMD(DAC, value):
    return DAC*0x10000 + 0x60000 + (int((value+2500.0)*65535.0/5000.0) & 0x0FFFF)


def add_qubit_resets(p, Qubits):
    # Set Biases to Reset, Zero
    initreset = []
    dac1s = []
    reset1 = []
    reset2 = []
    maxsettling = 7
    maxcount = 0
    for qid, qubit in enumerate(Qubits):
        # Set Flux to Reset and Squid to Zero
        initreset.extend([(('Flux',  qid+1), getCMD(1, qubit['Reset Bias 1'])),
                          (('Squid', qid+1), getCMD(1, qubit['Squid Zero']))])
        # Set Bias DACs to DAC 1
        dac1s.extend([(('Flux', qid+1), 0x50001), (('Squid', qid+1), 0x50001)])
        # Set Flux to Reset 1
        reset1.append((('Flux',  qid+1), getCMD(1, qubit['Reset Bias 1'])))
        # Set Flux to Reset 2
        reset2.append((('Flux',  qid+1), getCMD(1, qubit['Reset Bias 2'])))
        if qubit['Reset Settling Time'] > maxsettling:
            maxsettling = qubit['Reset Settling Time']
        if qubit['Reset Cycles'] > maxcount:
            maxcount = qubit['Reset Cycles']
    p.memory_bias_commands(initreset, T.Value(7.0, 'us'))
    p.memory_bias_commands(dac1s, T.Value(maxsettling, 'us'))
    for a in range(maxcount):
        p.memory_bias_commands(reset2, T.Value(maxsettling, 'us'))
        p.memory_bias_commands(reset1, T.Value(maxsettling, 'us'))
    pass

def add_qubit_inits(p, Qubits):
    # Reset Qubit
    add_qubit_resets(p, Qubits)
    # Go to Operating Bias
    setop = []
    maxsettling = 7
    for qid, qubit in enumerate(Qubits):
        setop.append((('Flux', qid+1), getCMD(1, qubit['Operating Bias'])))
        if qubit['Bias Settling Time'] > maxsettling:
            maxsettling = qubit['Bias Settling Time']
    p.memory_bias_commands(setop, T.Value(float(maxsettling), 'us'))

def add_squid_ramp(p, Qubit, qIndex=1):
    # Set Squid Bias to Ramp Start
    p.memory_bias_commands([(('Squid', qIndex), getCMD(1, Qubit['Squid Ramp Start']))],
                                    T.Value(7.0, 'us'))
    # Set Squid DAC to slow
    p.memory_bias_commands([(('Squid', qIndex), 0x50002)], T.Value(5.0, 'us'))
    # Start timer
    p.memory_start_timer([qIndex])
    # Set Squid Bias to Ramp End
    p.memory_bias_commands([(('Squid', qIndex), getCMD(1, Qubit['Squid Ramp End']))],
                                    Qubit['Squid Ramp Time'])
    # Set Biases to Zero
    p.memory_bias_commands([(('Flux',  qIndex), getCMD(1, 0)),
                                     (('Squid', qIndex), getCMD(1, Qubit['Squid Zero']))],
                                    T.Value(7.0, 'us'))
    # Stop timer
    p.memory_stop_timer([qIndex])
    # Set Squid DAC to fast
    p.memory_bias_commands([(('Squid', qIndex), 0x50001)],
                                    T.Value(5.0, 'us'))


def add_measurement(p, Qubit, qIndex=1):
    # Set Flux bias to measure point
    p.memory_bias_commands([(('Flux', qIndex), getCMD(1, Qubit['Measure Bias']))],
                                    Qubit['Measure Settling Time'])
    # Ramp Squid
    add_squid_ramp(p, Qubit, qIndex)


def add_goto_measure_biases(p, Qubits):
    setop = []
    maxsettling = 7
    for qid, qubit in enumerate(Qubits):
        setop.append((('Flux', qid+1), getCMD(1, qubit['Measure Bias'])))
        if qubit['Measure Settling Time'] > maxsettling:
            maxsettling = qubit['Measure Settling Time']
    p.memory_bias_commands(setop, T.Value(maxsettling, 'us'))


def getRange(selection, defmin, defmax, defstep):
    if selection is None:
        regmin  = defmin
        regmax  = defmax
        regstep = defstep
    else:
        regmin  =     selection[0].value
        regmax  =     selection[1].value
        regstep = abs(selection[2].value)
    if regmax < regmin:
        dummy  = regmin
        regmin = regmax
        regmax = dummy
    return regmin, regmax, regstep
   
def getStates(numqubits):
    states=[]
    for statenum in range(1, 2**numqubits):
        state = '>'
        for i in range(numqubits):
            if (statenum & (1 << i))>0:
                state = '1'+state
            else:
                state = '0'+state
        state = '|'+state
        states.append(state)
    return states    

class SetupNotFoundError(T.Error):
    code = 1
    def __init__(self, name):
        self.msg="Setup '%s' not found" % name

class ParameterNotFoundError(T.Error):
    code = 2
    def __init__(self, name):
        self.msg="Qubit parameter '%s' not found" % name

class NoSetupSelectedError(T.Error):
    """No experimental setup selected"""
    code = 3

class WrongQubitCountError(T.Error):
    code = 4
    def __init__(self, expt, qubitcount):
        self.msg="%s is a %d qubit experiment" % (expt, qubitcount)

class NoSessionSelectedError(T.Error):
    """No data-server session selected"""
    code = 3

class UndefinedSequenceError(T.Error):
    code = 5
    def __init__(self, name):
        self.msg="Sequence '%s' is not defined yet" % name

class MissingValueError(T.Error):
    code = 6
    def __init__(self, name):
        self.msg="Value for parameter '%s' is not given" % name


class ExperimentServer(LabradServer):
    name = 'Experiments'

    def getContext(self, base, index):
        if base not in self.ContextStack:
            self.ContextStack[base] = {}
        if not index in self.ContextStack[base]:
            self.ContextStack[base][index] = self.client.context()
        h, l = self.ContextStack[base][index]
        return (long(h), long(l))

    def getMyContext(self, base, index):
        if base not in self.ContextStack:
            self.ContextStack[base] = {}
        if not index in self.ContextStack[base]:
            ctxt = self.client.context()
            ctxt = (self.ID, ctxt[1])
            self.ContextStack[base][index] = ctxt
        h, l = self.ContextStack[base][index]
        return (long(h), long(l))

    def curQubit(self, ctxt):
        if 'Qubit' not in ctxt:
            raise NoQubitSelectedError()
        if ctxt['Qubit'] not in self.Qubits:
            raise NoQubitSelectedError()
        return self.Qubits[ctxt['Qubit']]

    def getQubit(self, name):
        if name not in self.Qubits:
            raise QubitNotFoundError(name)
        return self.Qubits[name]

    @inlineCallbacks
    def saveVariable(self, folder, name, variable):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Experiment Server', folder], True)
        p.set(name, repr(variable))
        ans = yield p.send()
        returnValue(ans.set)

    @inlineCallbacks
    def loadVariable(self, folder, name):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Experiment Server', folder], True)
        p.get(name)
        ans = yield p.send()
        data = T.evalLRData(ans.get)
        returnValue(data)

    @inlineCallbacks
    def listVariables(self, folder):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Experiment Server', folder], True)
        p.dir()
        ans = yield p.send()
        returnValue(ans.dir[1])

    def setupThreading(self, c):
        c['threads'] = [None] * 10
        c['threadID'] = 0

    def nextThreadContext(self, c):
        ctxt = self.getContext(c.ID, c['threadID'])
        return ctxt

    @inlineCallbacks
    def threadSend(self, c, dataHandler, packet, *parameters):
        if c['threads'][c['threadID']] is None:
            c['threads'][c['threadID']] = (packet.send(), parameters)
        else:
            send, pars = c['threads'][c['threadID']]
            results = yield send
            c['threads'][c['threadID']] = (packet.send(), parameters)
            dataHandler(results, *pars)
        c['threadID'] = (c['threadID'] + 1) % len(c['threads'])

    @inlineCallbacks
    def finishThreads(self, c, dataHandler):
        lastnonNone=-1
        while not (c['threadID'] == lastnonNone):
            if not (c['threads'][c['threadID']] is None):
                send, pars = c['threads'][c['threadID']]
                results = yield send
                dataHandler(results, *pars)
                c['threads'][c['threadID']] = None
                lastnonNone = c['threadID']
            if lastnonNone==-1:
                lastnonNone = c['threadID']
            c['threadID'] = (c['threadID'] + 1) % len(c['threads'])

    def checkSetup(self, c, name, qubitcnt=None):
        if 'Setup' not in c:
            raise NoSetupSelectedError()
        if 'Session' not in c:
            raise NoSessionSelectedError()
        if not ((qubitcnt is None) or (len(c['Qubits'])==qubitcnt)):
            raise WrongQubitCountError(name, qubitcnt)

    def add_qubit_parameters(self, p, qubit):
        if qubit in self.Qubits:
            for name, value in self.Qubits[qubit].items():
                p.add_parameter(qubit+' - '+name, value)

    def add_dataset_setup(self, p, session, name, indeps, deps):
        p.cd(['', 'Markus', 'Experiments' , session], True)
        p.new(name, indeps, deps)


    @inlineCallbacks
    def initServer(self):
        self.sequences={}
        self.ContextStack = {}
        self.qubitServer   = self.client.qubits
        self.dataServer    = self.client.data_vault
        self.anritsuServer = self.client.anritsu_server
        self.setups = yield self.qubitServer.setup_list()
        self.Qubits={}
        self.abort = False
        self.parameters={'Flux Limit Negative':                  T.Value(-2500, 'mV' ),
                         'Flux Limit Positive':                  T.Value( 2500, 'mV' ),
                         'Squid Zero':                           T.Value(    0, 'mV' ),
                         'Squid Ramp Start':                     T.Value(    0, 'mV' ),
                         'Squid Ramp End':                       T.Value( 2000, 'mV' ),
                         'Squid Ramp Time':                      T.Value(  100, 'us' ),
                         'Reset Settling Time':                  T.Value(   10, 'us' ),
                         'Bias Settling Time':                   T.Value(  200, 'us' ),
                         'Measure Settling Time':                T.Value(   50, 'us' ),
                         'Reset Bias 1':                         T.Value(    0, 'mV' ),
                         'Reset Bias 2':                         T.Value(    0, 'mV' ),
                         'Reset Cycles':                         T.Value(    1, ''   ),
                         'Measure Bias':                         T.Value( 1000, 'mV' ),
                         '1-State Cutoff':                       T.Value(   50, 'us' ),
                         'Operating Bias':                       T.Value( 1500, 'mV' ),
                         'Measure Pulse Length':                 T.Value(    3, 'ns' ),
                         'Measure Pulse Amplitude':              T.Value(  500, 'mV' ),
                         'Anritsu ID':                           T.Value(    0, ''   ),
                         'Measure Pulse Offset':                 T.Value(   50, 'ns' ),
                         'Resonance Frequency':                  T.Value(  6.5, 'GHz'),
                         'Sideband Frequency':                   T.Value(  100, 'MHz'),
                         'Pi-Pulse Length':                      T.Value(    9, 'ns' ),
                         'Pi-Pulse Amplitude':                   T.Value(    1, ''   )}
##                         'CalPoints Given':                      T.Value(    0, ''   ),
##                         'CalPoint 1 - Operating Bias':          T.Value(    0, 'mV' ),
##                         'CalPoint 1 - Resonance Frequency':     T.Value(    0, 'GHz'),
##                         'CalPoint 1 - Measure Pulse Amplitude': T.Value(    0, 'mV' ),
##                         'CalPoint 2 - Operating Bias':          T.Value(    0, 'mV' ),
##                         'CalPoint 2 - Resonance Frequency':     T.Value(    0, 'GHz'),
##                         'CalPoint 2 - Measure Pulse Amplitude': T.Value(    0, 'mV' ),
##                         'CalPoint 3 - Operating Bias':          T.Value(    0, 'mV' ),
##                         'CalPoint 3 - Resonance Frequency':     T.Value(    0, 'GHz'),
##                         'CalPoint 3 - Measure Pulse Amplitude': T.Value(    0, 'mV' )}

    def initContext(self, c):
        c['Stats'] = 300L
                         
    @setting(1, 'list experimental setups', returns=['*s'])
    def list_setups(self, c):
        self.setups = yield self.qubitServer.setup_list()
        returnValue(self.setups)

    @setting(2, 'select experimental setup', name=['s'], returns=['*s'])
    def select_setup(self, c, name):
        qubits, crap = yield self.qubitServer.experiment_new(name)
        c['Setup'] = name
        c['Qubits'] = qubits
        for qubit in qubits:
            if qubit not in self.Qubits:
                self.Qubits[qubit]=deepcopy(self.parameters)
        returnValue(qubits)

    @setting(5, 'Select Session', name=['s'], returns=['s'])
    def select_session(self, c, name):
        c['Session'] = name
        return name

    @setting(10, 'List Qubit Parameters', returns=['*s'])
    def list_parameters(self, c):
        return self.parameters.keys()

    @setting(11, 'Set Qubit Parameter', qubit=['s'], parameter=['s'], value=['v'])
    def set_parameter(self, c, qubit, parameter, value):
        if parameter not in self.parameters:
            raise ParameterNotFoundError(parameter)
        if qubit not in self.Qubits:
            self.Qubits[qubit]=deepcopy(self.parameters)
        if value.units != self.parameters[parameter].units:
            value = yield self.client.manager.convert_units(value, self.parameters[parameter].units)
        self.Qubits[qubit][parameter] = value

    @setting(12, 'Show Qubit Parameters', qubit=['s'], returns=['*s'])
    def show_parameters(self, c, qubit):
        if qubit not in self.Qubits:
            return []
        else:
            maxlen = 0
            for name in self.Qubits[qubit].keys():
                if len(name)>maxlen:
                    maxlen = len(name)
            return ["%s: %s%s" % (name, ' '*(maxlen-len(name)), str(value))
                    for name, value in self.Qubits[qubit].items()]

    @setting(13, 'Get Qubit Parameters', qubit=['s'], returns=['*(svs)'])
    def get_parameters(self, c, qubit):
        if qubit not in self.Qubits:
            return []
        else:
            maxlen = 0
            for name in self.Qubits[qubit].keys():
                if len(name)>maxlen:
                    maxlen = len(name)
            return [(name, float(value), str(value.units))
                    for name, value in self.Qubits[qubit].items()]



    @setting(22, 'List Qubits', returns=['*s'])
    def list_qubits(self, c):
        return self.Qubits.keys()



    @setting(25, 'Qubit Save', qubit=['s'], returns=['s'])
    def save_qubit(self, c, qubit):
        if qubit not in self.Qubits:
            raise QubitNotFoundError(qubit)
        yield self.saveVariable('Qubits', qubit, self.Qubits[qubit])
        returnValue(qubit)



    @setting(26, 'Qubit Load', qubit=['s'], returns=['s'])
    def load_qubit(self, c, qubit):
        data = yield self.loadVariable('Qubits', qubit)
        self.Qubits[qubit]=deepcopy(self.parameters)
        self.Qubits[qubit].update(data)
        returnValue(repr(self.Qubits[qubit]))



    @setting(27, 'List Saved Qubits', returns=['*s'])
    def list_saved_qubits(self, c):
        qubits = yield self.listVariables('Qubits')
        returnValue(qubits)


    @setting(98, 'Abort Scan')
    def abort_scan(self, c):
        """Aborts all currently running scans in all contexts"""
        self.abort = True
        

    @setting(99, 'Stats', stats=['w'])
    def stats(self, c, stats):
        """Selects stats"""
        c['Stats']=stats

        

    @setting(100, 'Squid Steps', region=['(v[mV]{start}, v[mV]{end}, v[mV]{steps})', ''],
                                 returns=['*ss'])
    def squid_steps(self, c, region):
        self.checkSetup(c, 'Squidsteps', 1)

        qubit = c['Qubits'][0]
        
        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], 'Squid Steps on %s' % qubit, ['Flux [mV]'],
                               ['Switching Time (negative) [us]', 'Switching Time (positive) [us]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Data handling function
        switchings = {}
        def handleData(results, flux, reset):
            if flux in switchings:
                d = [[flux, a/25.0, b/25.0]
                      for a, b in zip(switchings[flux], results.run[0])]
                self.dataServer.add(d, context = c.ID)
                del switchings[flux]
            else:
                switchings[flux] = results.run[0]

        # Take data
        fluxneg = self.Qubits[qubit]['Flux Limit Negative']
        fluxpos = self.Qubits[qubit]['Flux Limit Positive']
        
        self.setupThreading(c)

        fluxmin, fluxmax, fluxstep = getRange(region, fluxneg, fluxpos, 100)
            
        flux=fluxmin
        self.abort = False
        while (flux<=fluxmax) and not self.abort:
            for reset in [fluxneg, fluxpos]:
                p = self.qubitServer.packet(context = self.nextThreadContext(c))
                
                p.experiment_new(c['Setup'])
                # Set Biases to Reset, Zero
                p.memory_bias_commands([(('Flux',  1), getCMD(1, reset)),
                                                 (('Squid', 1), getCMD(1, self.Qubits[qubit]['Squid Zero']))],
                                                T.Value(7.0, 'us'))
                # Select DAC 1 fast for flux and squid
                p.memory_bias_commands([(('Flux',  1), 0x50001),
                                                 (('Squid', 1), 0x50001)],
                                                self.Qubits[qubit]['Reset Settling Time'])
                # Set Flux bias to Measure
                p.memory_bias_commands([(('Flux',  1), getCMD(1, flux))],
                                                self.Qubits[qubit]['Measure Settling Time'])
                # Squid Ramp
                add_squid_ramp(p, self.Qubits[qubit])
                p.run(c['Stats'])

                yield self.threadSend(c, handleData, p, flux, reset)
            flux += fluxstep

        yield self.finishThreads(c, handleData)

        returnValue(name)


    # Default data handling function
    def handleSwitchingData(self, results, cutoffvals, cID, *scanpos):
        total = len(results.run[0])
        states = [0]*total
        for i, coval in enumerate(cutoffvals):
            statemask = 1 << i
            cutoff = abs(coval)*25
            negate = coval<0      
            for ofs, a in enumerate(results.run[i]):
                if (a>cutoff) ^ negate:
                    states[ofs]|=statemask
        counts = [0]*((1 << len(cutoffvals))-1)
        for state in states:
            if state>0:
                counts[state-1]+=1
        d = list(scanpos) + [100.0*c/total for c in counts]
        self.dataServer.add(d, context = cID)



    @setting(110, 'Step Edge', region=['(v[mV]{start}, v[mV]{end}, v[mV]{steps})', ''],
                               returns=['*ss'])
    def step_edge(self, c, region):
        self.checkSetup(c, 'Step Edge', 1)

        qubit = c['Qubits'][0]

        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], 'Step Edge on %s' % qubit, ['Flux [mV]'],
                               ['Probability (|1>) [%]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        fluxmin, fluxmax, fluxstep = getRange(region, self.Qubits[qubit]['Flux Limit Negative'],
                                                      self.Qubits[qubit]['Flux Limit Positive'],
                                                      100)
        cutoffs = [self.Qubits[qubit]['1-State Cutoff']]
        flux=fluxmin
        self.abort = False
        while (flux<=fluxmax) and not self.abort:
            p = self.qubitServer.packet(context = self.nextThreadContext(c))

            p.experiment_new(c['Setup'])
            # Reset Qubit
            add_qubit_resets(p, [self.Qubits[qubit]])
            # Go to Operating Bias
            p.memory_bias_commands([(('Flux',  1), getCMD(1, flux))],
                                            self.Qubits[qubit]['Bias Settling Time'])
            # Measure
            add_measurement(p, self.Qubits[qubit])
            p.run(c['Stats'])

            yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, flux)
            flux += fluxstep

        yield self.finishThreads(c, self.handleSwitchingData)

        returnValue(name)



    @setting(120, 'S-Curve', region=['(v[mV]{start}, v[mV]{end}, v[mV]{steps})', ''],
                             returns=['*ss'])
    def s_curve(self, c, region):
        self.checkSetup(c, 'S-Curve', 1)

        qubit = c['Qubits'][0]

        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], 'S-Curve on %s' % qubit, ['Measure Pulse Amplitude [mV]'],
                               ['Probability (|1>) [%]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        ampmin, ampmax, ampstep = getRange(region, 0, 1000, 25)

        cutoffs = [self.Qubits[qubit]['1-State Cutoff']]
        amp=ampmin
        self.abort = False
        mplen = int(self.Qubits[qubit]['Measure Pulse Length'])
        while (amp<=ampmax) and not self.abort:
            p = self.qubitServer.packet(context = self.nextThreadContext(c))

            p.experiment_new(c['Setup'])
            # Initialize Qubit
            add_qubit_inits(p, [self.Qubits[qubit]])
            # Set up a trigger for the scope
            p.sram_trigger_pulse(('Trigger', 1), 25)
            # Send Measure Pulse
            p.sram_analog_delay(('Measure', 1), 200)
            p.sram_analog_data (('Measure', 1), [amp/1000.0]*mplen)
            p.memory_call_sram()
            # Readout
            add_measurement(p, self.Qubits[qubit])
            p.run(c['Stats'])

            yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, amp)
            amp += ampstep

        yield self.finishThreads(c, self.handleSwitchingData)

        returnValue(name)



    @setting(130, 'Spectroscopy', power=['v[dBm]'], region=['(v[GHz]{start}, v[GHz]{end}, v[MHz]{steps})'],
                                  returns=['*ss'])
    def spectroscopy(self, c, power, region = None):
        self.checkSetup(c, 'Spectroscopy', None)

        axes  = ['Probability (%s) [%%]' % stname for stname in getStates(len(c['Qubits']))]

        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], 'Spectroscopy on %s' % c['Setup'], ['Frequency [GHz]'], axes)
        for qubit in c['Qubits']:
            self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)
        
        if not(region is None):
            region = list(region)
            region[2] = region[2].inUnitsOf('GHz')

        frqmin, frqmax, frqstep = getRange(region, 5.0, 10.0, 0.1)

        cutoffs = [self.Qubits[qubit]['1-State Cutoff'] for qubit in c['Qubits']]
        frq=frqmin
        self.abort = False
        mplen = dict([(qubit, int(self.Qubits[qubit]['Measure Pulse Length'   ]      )) for qubit in c['Qubits']])
        mpamp = dict([(qubit,     self.Qubits[qubit]['Measure Pulse Amplitude']/1000.0) for qubit in c['Qubits']])
        while (frq<frqmax+(frqstep/3.0)) and not self.abort:
            p = self.qubitServer.packet(context = self.nextThreadContext(c))
            
            p.experiment_new(c['Setup'])
            # Initialize Qubits
            add_qubit_inits(p, [self.Qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                # Set up Anritsu
                p.experiment_set_anritsu(('uWaves', i+1), T.Value(frq, 'GHz'), power)
                # Set up a trigger for the scope
                p.sram_trigger_pulse(('Trigger', i+1), 25)
                # Send uWave Pulse
                p.sram_iq_delay    (('uWaves',  i+1), 200, False)
                p.sram_iq_data     (('uWaves',  i+1), [1]*2000, False)
                # Send Measure Pulse
                p.sram_analog_delay(('Measure', i+1), 2200)
                p.sram_analog_data (('Measure', i+1), [mpamp[qubit]]*mplen[qubit])
            p.memory_call_sram()
            # Readout
            add_goto_measure_biases(p, [self.Qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                if i>0:
                    p.memory_delay(T.Value(200,'us'))
                add_squid_ramp(p, self.Qubits[qubit], i+1)
            # Run experiment
            p.run(c['Stats'])

            yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, frq)
            frq += frqstep

        yield self.finishThreads(c, self.handleSwitchingData)
        
        returnValue(name)



    @setting(140, 'Rabi', amplitude=['v[]'], region=['(v[ns]{start}, v[ns]{end}, v[ns]{steps})'],
                          returns=['*ss'])
    def rabi(self, c, amplitude, region = None):
        self.checkSetup(c, 'Rabi', 1)

        qubit = c['Qubits'][0]

        sbmix = self.Qubits[qubit]['Sideband Frequency']
        frq = self.Qubits[qubit]['Resonance Frequency'] - sbmix

        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], 'Rabi on %s' % qubit, ['Rabi Length [ns]'],
                               ['Probability (|1>) [%]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        timemin, timemax, timestep = getRange(region, 0, 1000, 1)

        cutoffs = [self.Qubits[qubit]['1-State Cutoff']]
        time=timemin
        self.abort = False
        mplen = int(self.Qubits[qubit]['Measure Pulse Length'   ])
        mpamp =     self.Qubits[qubit]['Measure Pulse Amplitude']/1000.0
        mpofs = int(self.Qubits[qubit]['Measure Pulse Offset'   ])
        while (time<=timemax) and not self.abort:
            p = self.qubitServer.packet(context = self.nextThreadContext(c))

            p.experiment_new(c['Setup'])
            # Set up Anritsu
            p.experiment_set_anritsu(('uWaves', 1), frq, T.Value(2.7,'dBm'))
            # Initialize Qubit
            add_qubit_inits(p, [self.Qubits[qubit]])
            # Add trigger
            p.sram_trigger_pulse(('Trigger', 1), 25)
            # Send uWave Pulse
            p.sram_iq_delay   (('uWaves', 1), 200)
            p.sram_iq_envelope(('uWaves', 1), [amplitude]*int(time), sbmix, 0)
            # Send Measure Pulse
            p.sram_analog_delay(('Measure', 1), time+mpofs+200)
            p.sram_analog_data (('Measure', 1), [mpamp]*mplen)
            p.memory_call_sram()
            # Readout
            add_measurement(p, self.Qubits[qubit])
            p.run(c['Stats'])

            yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, time)
            time += timestep

        yield self.finishThreads(c, self.handleSwitchingData)

        returnValue(name)



    @setting(150, 'T1', region=['(v[ns]{start}, v[ns]{end}, v[ns]{steps})'],
                          returns=['*ss'])
    def t1(self, c, region = None):
        self.checkSetup(c, 'Spectroscopy', None)

        axes  = ['Probability (%s) [%%]' % stname for stname in getStates(len(c['Qubits']))]

        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], 'T1-Sweep on %s' % c['Setup'], ['Frequency [GHz]'], axes)
        for qubit in c['Qubits']:
            self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)
        
        timemin, timemax, timestep = getRange(region, 0, 1000, 1)

        cutoffs = [self.Qubits[qubit]['1-State Cutoff'] for qubit in c['Qubits']]
        time=timemin
        self.abort = False
        mpofs = dict([(qubit, int(self.Qubits[qubit]['Measure Pulse Offset'   ]      )) for qubit in c['Qubits']])
        mplen = dict([(qubit, int(self.Qubits[qubit]['Measure Pulse Length'   ]      )) for qubit in c['Qubits']])
        mpamp = dict([(qubit,     self.Qubits[qubit]['Measure Pulse Amplitude']/1000.0) for qubit in c['Qubits']])
        pilen = dict([(qubit, int(self.Qubits[qubit]['Pi-Pulse Length'        ]      )) for qubit in c['Qubits']])
        piamp = dict([(qubit,     self.Qubits[qubit]['Pi-Pulse Amplitude'     ]       ) for qubit in c['Qubits']])
        sbmix = dict([(qubit,     self.Qubits[qubit]['Sideband Frequency'     ]       ) for qubit in c['Qubits']])
        rfreq = dict([(qubit,     self.Qubits[qubit]['Resonance Frequency'    ]       ) for qubit in c['Qubits']])
        while (time<=timemax) and not self.abort:
            p = self.qubitServer.packet(context = self.nextThreadContext(c))
            
            p.experiment_new(c['Setup'])
            # Initialize Qubits
            add_qubit_inits(p, [self.Qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                # Set up Anritst
                p.experiment_set_anritsu(('uWaves', i+1), rfreq[qubit]-sbmix[qubit], T.Value(2.7,'dBm'))
                # Set up a trigger for the scope
                p.sram_trigger_pulse(('Trigger', i+1), 25)
                # Send uWave Pulse
                p.sram_iq_delay   (('uWaves', i+1), 200)
                p.sram_iq_envelope(('uWaves', i+1), [piamp[qubit]]*pilen[qubit], sbmix[qubit], 0)
                # Send Measure Pulse
                p.sram_analog_delay(('Measure', i+1), time+mpofs[qubit]+200)
                p.sram_analog_data (('Measure', i+1), [mpamp[qubit]]*mplen[qubit])
            p.memory_call_sram()
            add_goto_measure_biases(p, [self.Qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                if i>0:
                    p.memory_delay(T.Value(200,'us'))
                add_squid_ramp(p, self.Qubits[qubit], i+1)
            # Set anritsu frequency and run experiment
            p.run(c['Stats'])

            yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, time)
            time += timestep

        yield self.finishThreads(c, self.handleSwitchingData)
        
        returnValue(name)

        

    @setting(200, 'New Sequence', name=['s'], qubitcount=['w'],
                                  returns=[''])
    def define_sequence(self, c, name, qubitcount=1):
        info={'QubitCount':qubitcount,
              'Operations':[]}
        self.sequences={name: info}
        c['Sequence']=name
        return

    
        
    @setting(201, 'Add Operation', name=['s'], channel=['(sw)'], parameters=['?{(ss)(vs)...}'], returns=[''])
    def add_operation(self, c, name, channel, parameters):
        info = self.sequences[c['Sequence']]
        info['Operations'].append((name, channel, list(parameters)))
        return



    @setting(202, 'Sequence Save', name=['s'], returns=['s'])
    def save_sequence(self, c, name):
        if name not in self.sequences:
            raise QubitNotFoundError(name)
        yield self.saveVariable('Sequences', name, self.sequences[name])
        returnValue(name)



    @setting(203, 'Sequence Load', name=['s'], returns=['s'])
    def load_sequence(self, c, name):
        data = yield self.loadVariable('Sequences', name)
        self.sequences[name]={'QubitCount':1, 'Operations':[]}
        self.sequences[name].update(data)
        returnValue(repr(self.sequences[name]))



    @setting(204, 'List Saved Sequence', returns=['*s'])
    def list_saved_sequences(self, c):
        names = yield self.listVariables('Sequences')
        returnValue(names)



    def getValue(self, name, qubit, given={}, units=None):
        if not isinstance(name, str):
            return name
        result = None
        if name in given:
            result = given[name]
        if (result is None) and (name in self.Qubits[qubit]):
            result = self.Qubits[qubit][name]
        if result is None:
            raise MissingValueError(name)
            
        if isinstance(result, T.Value) and not (units is None):
#            print result, units
            return result.inUnitsOf(units).value
        return result



    def addOperations(self, pkt, ops, qubits, given={}):
        for name, channel, parameters in ops:
            qubit = qubits[channel[1]-1]
#            print parameters, given
            params = [self.getValue(p[0], qubit, given, p[1]) for p in parameters]
#            print params
            if channel[0]=='uWaves':
                if name=='Slepian':
                    pkt.sram_iq_slepian (channel, params[0], params[1], params[2], params[3])
                if name=='TopHat':
                    pkt.sram_iq_envelope(channel, [params[0]]*int(params[1]), params[2], params[3])
                if name=='Delay':
                    pkt.sram_iq_delay   (channel, params[0])
                    
            if channel[0]=='Measure':
                if name=='Delay':
                    pkt.sram_analog_delay(channel, params[0])
                if name=='TopHat':
                    pkt.sram_analog_data (channel, [params[0]]*int(params[1]))
                if name=='Ramp':
                    data=[params[0]+i*(params[1]-params[0])/params[2] for i in range(int(params[2]))]
                    pkt.sram_analog_data (channel, data)
                    
        
    @setting(210, 'Run 1D Sweep', sequencename=['s'], sweepvariable=['s'],
                                  sweep=['(v{start}v{end}v{steps})'], returns=['*ss'])
    def sweep_1d(self, c, sequencename, sweepvariable, sweep):
        if not sequencename in self.sequences:
            raise UndefinedSequenceError(sequencename)
        seqinfo = self.sequences[sequencename]
        self.checkSetup(c, sequencename, seqinfo['QubitCount'])

        axes  = ['Probability (%s) [%%]' % stname for stname in getStates(len(c['Qubits']))]

        if isinstance(sweep[0], T.Value):
            units = sweep[0].units
        else:
            units = ''
        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], '%s on %s' % (sequencename, c['Setup']), [(sweepvariable, units)], axes)
        for qubit in c['Qubits']:
            self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        cutoffs = [self.Qubits[qubit]['1-State Cutoff'] for qubit in c['Qubits']]
        self.abort = False
        mpofs = dict([(qubit, int(self.Qubits[qubit]['Measure Pulse Offset'   ]      )) for qubit in c['Qubits']])
        sbmix = dict([(qubit,     self.Qubits[qubit]['Sideband Frequency'     ]       ) for qubit in c['Qubits']])
        rfreq = dict([(qubit,     self.Qubits[qubit]['Resonance Frequency'    ]       ) for qubit in c['Qubits']])
        
        sweepvar = sweep[0]
        while (sweepvar<=sweep[1]) and not self.abort:
            p = self.qubitServer.packet(context = self.nextThreadContext(c))
            c['Qubits']
            p.experiment_new(c['Setup'])
            # Initialize Qubits
            add_qubit_inits(p, [self.Qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                # Set up Anritsu
                p.experiment_set_anritsu(('uWaves', i+1), rfreq[qubit]-sbmix[qubit], T.Value(2.7,'dBm'))
                # Set up a trigger for the scope
                p.sram_trigger_pulse(('Trigger', i+1), 25)
                # Add a base delay for all channels
                p.sram_iq_delay     (('uWaves' , i+1), 200)
                p.sram_analog_delay (('Measure', i+1), mpofs[qubit]+200)
                
            # Add experiment sequence
            self.addOperations(p, seqinfo['Operations'], c['Qubits'], {sweepvariable: sweepvar})
            
            # Finish up memory
            p.memory_call_sram()
            add_goto_measure_biases(p, [self.Qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                if i>0:
                    p.memory_delay(T.Value(200,'us'))
                add_squid_ramp(p, self.Qubits[qubit], i+1)
            # Run experiment
            p.run(c['Stats'])

            yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, sweepvar)
            sweepvar += sweep[2]

        yield self.finishThreads(c, self.handleSwitchingData)
        
        returnValue(name)
                    
        
    @setting(211, 'Run 2D Sweep', sequencename=['s'], sweepvariable1=['s'],
                                  sweep1=['(v{start}v{end}v{steps})'], sweepvariable2=['s'],
                                  sweep2=['(v{start}v{end}v{steps})'], returns=['*ss'])
    def sweep_2d(self, c, sequencename, sweepvariable1, sweep1, sweepvariable2, sweep2):
        if not sequencename in self.sequences:
            raise UndefinedSequenceError(sequencename)
        seqinfo = self.sequences[sequencename]
        self.checkSetup(c, sequencename, seqinfo['QubitCount'])

        axes  = ['Probability (%s) [%%]' % stname for stname in getStates(len(c['Qubits']))]

        if isinstance(sweep1[0], T.Value):
            units1 = sweep1[0].units
        else:
            units1 = ''
        if isinstance(sweep2[0], T.Value):
            units2 = sweep2[0].units
        else:
            units2 = ''
        # Setup dataset
        p = self.dataServer.packet(context = c.ID)
        self.add_dataset_setup(p, c['Session'], '%s on %s' % (sequencename, c['Setup']), [(sweepvariable1, units1), (sweepvariable2, units2)], axes)
        for qubit in c['Qubits']:
            self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        cutoffs = [self.Qubits[qubit]['1-State Cutoff'] for qubit in c['Qubits']]
        self.abort = False
        mpofs = dict([(qubit, int(self.Qubits[qubit]['Measure Pulse Offset'   ]      )) for qubit in c['Qubits']])
        sbmix = dict([(qubit,     self.Qubits[qubit]['Sideband Frequency'     ]       ) for qubit in c['Qubits']])
        rfreq = dict([(qubit,     self.Qubits[qubit]['Resonance Frequency'    ]       ) for qubit in c['Qubits']])
        
        sweepvar2 = sweep2[0]
        while (sweepvar2<=sweep2[1]) and not self.abort:
            sweepvar1 = sweep1[0]
            while (sweepvar1<=sweep1[1]) and not self.abort:
                p = self.qubitServer.packet(context = self.nextThreadContext(c))
                c['Qubits']
                p.experiment_new(c['Setup'])
                # Initialize Qubits
                add_qubit_inits(p, [self.Qubits[qubit] for qubit in c['Qubits']])
                for i, qubit in enumerate(c['Qubits']):
                    # Set up Anritsu
                    p.experiment_set_anritsu(('uWaves', i+1), rfreq[qubit]-sbmix[qubit], T.Value(2.7,'dBm'))
                    # Set up a trigger for the scope
                    p.sram_trigger_pulse(('Trigger', i+1), 25)
                    # Add a base delay for all channels
                    p.sram_iq_delay     (('uWaves' , i+1), 200)
                    p.sram_analog_delay (('Measure', i+1), mpofs[qubit]+200)
                    
                # Add experiment sequence
                self.addOperations(p, seqinfo['Operations'], c['Qubits'], {sweepvariable1: sweepvar1, sweepvariable2: sweepvar2})
                
                # Finish up memory
                p.memory_call_sram()
                add_goto_measure_biases(p, [self.Qubits[qubit] for qubit in c['Qubits']])
                for i, qubit in enumerate(c['Qubits']):
                    if i>0:
                        p.memory_delay(T.Value(200,'us'))
                    add_squid_ramp(p, self.Qubits[qubit], i+1)
                # Run experiment
                p.run(c['Stats'])

                yield self.threadSend(c, self.handleSwitchingData, p, cutoffs, c.ID, sweepvar1, sweepvar2)
                sweepvar1 += sweep1[2]
            sweepvar2 += sweep2[2]

        yield self.finishThreads(c, self.handleSwitchingData)
        
        returnValue(name)


__server__ = ExperimentServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
