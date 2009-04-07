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
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredSemaphore

from datetime import datetime

import numpy

CHANNELS = ['ch1', 'ch2']
NTHREADS = 10

def getCMD(DAC, value):
    return DAC*0x10000 + 0x60000 + (int((value+2500.0)*65535.0/5000.0) & 0x0FFFF)


def add_qubit_resets(p, qubits):
    # Set Biases to Reset, Zero
    initreset = []
    dac1s = []
    reset1 = []
    reset2 = []
    
    # create the bias commands for each qubit
    for qid, qubit in enumerate(qubits):
        # Set Flux to Reset and Squid to Zero
        initreset.extend([(('Flux',  qid+1), getCMD(1, qubit['Reset Bias 1'])),
                          (('Squid', qid+1), getCMD(1, qubit['Squid Zero']))])
        # Set Bias DACs to DAC 1
        dac1s.extend([(('Flux', qid+1), 0x50001), (('Squid', qid+1), 0x50001)])
        # Set Flux to Reset 1
        reset1.append((('Flux',  qid+1), getCMD(1, qubit['Reset Bias 1'])))
        # Set Flux to Reset 2
        reset2.append((('Flux',  qid+1), getCMD(1, qubit['Reset Bias 2'])))
    
    # find maximum required settling time and reset count    
    maxsettling = max(max(q['Reset Settling Time'] for q in qubits), 7)
    maxcount = max(q['Reset Cycles'] for q in qubits)
    
    # add the commands to be sent to the experiment server
    p.experiment_send_bias_commands(initreset, T.Value(7.0, 'us'))
    p.experiment_send_bias_commands(dac1s, T.Value(maxsettling, 'us'))
    for a in range(maxcount):
        p.experiment_send_bias_commands(reset2, T.Value(maxsettling, 'us'))
        p.experiment_send_bias_commands(reset1, T.Value(maxsettling, 'us'))

def add_qubit_inits(p, qubits):
    # create bias commands for each qubit
    setop = [(('Flux', qid+1), getCMD(1, qubit['Operating Bias']))
             for qid, qubit in enumerate(qubits)]
        
    # find maximum settling time
    maxsettling = max(max(q['Reset Settling Time'] for q in qubits), 7)
    
    # reset
    add_qubit_resets(p, qubits)
    
    # go to operating bias
    p.experiment_send_bias_commands(setop, T.Value(maxsettling, 'us'))

def add_squid_ramp(p, qubit, qIndex=1):
    # Set Squid Bias to Ramp Start
    p.experiment_send_bias_commands([(('Squid', qIndex), getCMD(1, qubit['Squid Ramp Start']))],
                                    T.Value(7.0, 'us'))
    # Set Squid DAC to slow
    p.experiment_send_bias_commands([(('Squid', qIndex), 0x50002)], T.Value(5.0, 'us'))
    # Start timer
    p.experiment_start_timer([qIndex])
    # Set Squid Bias to Ramp End
    p.experiment_send_bias_commands([(('Squid', qIndex), getCMD(1, qubit['Squid Ramp End']))],
                                    qubit['Squid Ramp Time'])
    # Set Biases to Zero
    p.experiment_send_bias_commands([(('Flux',  qIndex), getCMD(1, 0)),
                                     (('Squid', qIndex), getCMD(1, qubit['Squid Zero']))],
                                    T.Value(7.0, 'us'))
    # Stop timer
    p.experiment_stop_timer([qIndex])
    # Set Squid DAC to fast
    p.experiment_send_bias_commands([(('Squid', qIndex), 0x50001)],
                                    T.Value(5.0, 'us'))


def add_measurement(p, qubit, qIndex=1):
    # Set Flux bias to measure point
    p.experiment_send_bias_commands([(('Flux', qIndex), getCMD(1, qubit['Measure Bias']))],
                                    qubit['Measure Settling Time'])
    # Ramp Squid
    add_squid_ramp(p, qubit, qIndex)


def add_goto_measure_biases(p, Qubits):
    # create bias commands for each qubit
    setop = [(('Flux', qid+1), getCMD(1, qubit['Measure Bias']))
             for qid, qubit in enumerate(qubits)]
        
    # find maximum settling time
    maxsettling = max(max(q['Measure Settling Time'] for q in qubits), 7)
            
    p.experiment_send_bias_commands(setop, T.Value(maxsettling, 'us'))


def getRange(selection, defmin, defmax, defstep):
    if selection is None:
        regmin  = defmin
        regmax  = defmax
        regstep = defstep
    else:
        regmin, regmax, regstep = selection
        regstep = abs(regstep)
    if regmax < regmin:
        regmin, regmax = regmax, regmin
    return regmin, regmax, regstep
   
def binary_digits(i, N):
    return [(i >> k) % 2 for k in reversed(range(N))]

def binary_string(i, N):
    return ''.join(str(d) for d in binary_digits(i, N))
   
def getStates(numqubits):
    return ['|' + binary_string(i, numqubits) + '>' for i in range(2**numqubits)]

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


class ExperimentServer(LabradServer):
    name = 'Test Experiments'
    
    def getContext(self, base, index):
        if base not in self.ContextStack:
            self.ContextStack[base] = {}
        if not index in self.ContextStack[base]:
            self.ContextStack[base][index] = self.client.context()
        return self.ContextStack[base][index]

    def getMyContext(self, base, index):
        if base not in self.ContextStack:
            self.ContextStack[base] = {}
        if not index in self.ContextStack[base]:
            ctxt = self.client.context()
            ctxt = self.ID, ctxt[1]
            self.ContextStack[base][index] = ctxt
        return self.ContextStack[base][index]

    def curQubit(self, ctxt):
        if 'Qubit' not in ctxt:
            raise NoQubitSelectedError()
        if ctxt['Qubit'] not in self.qubits:
            raise NoQubitSelectedError()
        return self.qubits[ctxt['Qubit']]

    def getQubit(self, name):
        if name not in self.qubits:
            raise QubitNotFoundError(name)
        return self.qubits[name]

    @inlineCallbacks
    def saveVariable(self, folder, name, variable):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Test Experiment Server', folder], True)
        p.set(name, repr(variable))
        ans = yield p.send()
        returnValue(ans.set)

    @inlineCallbacks
    def loadVariable(self, folder, name):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Test Experiment Server', folder], True)
        p.get(name)
        ans = yield p.send()
        data = T.evalLRData(ans.get)
        returnValue(data)

    @inlineCallbacks
    def listVariables(self, folder):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Test Experiment Server', folder], True)
        p.dir()
        ans = yield p.send()
        returnValue(ans.dir[1])

    def setupThreading(self, c):
        c['threads'] = []

    @inlineCallbacks
    def threadSend(self, c, dataHandler, packet, *parameters):
        if len(self.freeContexts):
            ctx = self.freeContexts.pop()
        else:
            ctx = self.client.context()
        threads = c['threads']
        if len(threads) < NTHREADS:
            threads.append((packet.send(context=ctx), parameters, ctx))
        else:
            send, pars, freectx = threads.pop(0)
            results = yield send
            threads.append((packet.send(context=ctx), parameters, ctx))
            self.freeContexts.add(freectx)
            dataHandler(results, *pars)

    @inlineCallbacks
    def finishThreads(self, c, dataHandler):
        for send, pars, freectx in c['threads']:
            results = yield send
            self.freeContexts.add(freectx)
            dataHandler(results, *pars)

    def checkSetup(self, c, name, qubitcnt=None):
        if 'Setup' not in c:
            raise NoSetupSelectedError()
        if 'Session' not in c:
            raise NoSessionSelectedError()
        if qubitcnt is not None and qubitcnt != len(c['Qubits']):
            raise WrongQubitCountError(name, qubitcnt)

    def add_qubit_parameters(self, p, qubit):
        if qubit in self.qubits:
            for name, value in self.qubits[qubit].items():
                p.add_parameter(qubit+' - '+name, value)

    def add_dataset_setup(self, p, session, name, indeps, deps):
        p.cd(['', 'Markus', 'Experiments' , session], True)
        p.new(name, indeps, deps)


    @inlineCallbacks
    def initServer(self):
        self.ContextStack = {}
        self.freeContexts = set()
        self.qubitServer = self.client.qubits
        self.dataServer = self.client.data_vault
        self.anritsuServer = self.client.anritsu_server
        self.setups = yield self.qubitServer.list_experimental_setups()
        self.qubits = {}
        self.abort = False
        self.parameters = {'Flux Limit Negative':    T.Value(-2500, 'mV' ),
                           'Flux Limit Positive':    T.Value( 2500, 'mV' ),
                           'Squid Zero':             T.Value(    0, 'mV' ),
                           'Squid Ramp Start':       T.Value(    0, 'mV' ),
                           'Squid Ramp End':         T.Value( 2000, 'mV' ),
                           'Squid Ramp Time':        T.Value(  100, 'us' ),
                           'Reset Settling Time':    T.Value(   10, 'us' ),
                           'Bias Settling Time':     T.Value(  200, 'us' ),
                           'Measure Settling Time':  T.Value(   50, 'us' ),
                           'Reset Bias 1':           T.Value(    0, 'mV' ),
                           'Reset Bias 2':           T.Value(    0, 'mV' ),
                           'Reset Cycles':           T.Value(    1, ''   ),
                           'Measure Bias':           T.Value( 1000, 'mV' ),
                           '1-State Cutoff':         T.Value(   50, 'us' ),
                           'Operating Bias':         T.Value( 1500, 'mV' ),
                           'Measure Pulse Length':   T.Value(    3, 'ns' ),
                           'Measure Pulse Amplitude':T.Value(  500, 'mV' ),
                           'Anritsu ID':             T.Value(    0, ''   ),
                           'Measure Pulse Offset':   T.Value(   50, 'ns' ),
                           'Resonance Frequency':    T.Value(  6.5, 'GHz'),
                           'Sideband Frequency':     T.Value(  100, 'MHz'),
                           'Pi-Pulse Length':        T.Value(    9, 'ns' ),
                           'Pi-Pulse Amplitude':     T.Value(    1, ''   )}

    def initContext(self, c):
        c['Stats'] = 300L
                         
    @setting(1, 'list experimental setups', returns=['*s'])
    def list_setups(self, c):
        self.setups = yield self.qubitServer.list_experimental_setups()
        returnValue(self.setups)

    @setting(2, 'select experimental setup', name=['s'], returns=['*s'])
    def select_setup(self, c, name):
        qubits, crap = yield self.qubitServer.experiment_new(name)
        c['Setup'] = name
        c['Qubits'] = qubits
        for qubit in qubits:
            if qubit not in self.qubits:
                self.qubits[qubit] = dict(self.parameters)
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
        if qubit not in self.qubits:
            self.qubits[qubit] = dict(self.parameters)
        units = self.parameters[parameter].units
        if value.units != units:
            value = yield self.client.manager.convert_units(value, units)
        self.qubits[qubit][parameter] = value

    @setting(12, 'Show Qubit Parameters', name=['s'], returns=['*s'])
    def show_parameters(self, c, name):
        qubit = self.getQubit(name)
        maxlen = max(len(param) for param in self.qubits[qubit].keys())
        return ["%s: %s%s" % (param, ' '*(maxlen-len(param)), value)
                for param, value in qubit.items()]

    @setting(13, 'Get Qubit Parameters', name=['s'], returns=['*(svs)'])
    def get_parameters(self, c, name):
        qubit = self.getQubit(name)
        return [(param, value, value.units)
                for param, value in qubit.items()]

    @setting(22, 'List Qubits', returns=['*s'])
    def list_qubits(self, c):
        return self.qubits.keys()


    @setting(25, 'Qubit Save', name=['s'], returns=['s'])
    def save_qubit(self, c, name):
        qubit = self.getQubit(name)
        return self.saveVariable('Qubits', name, qubit)



    @setting(26, 'Qubit Load', name=['s'], returns=['s'])
    def load_qubit(self, c, name):
        data = yield self.loadVariable('Qubits', name)
        qubit = dict(self.parameters)
        qubit.update(data)
        self.qubits[name] = qubit
        returnValue(repr(qubit))



    @setting(27, 'List Saved Qubits', returns=['*s'])
    def list_saved_qubits(self, c):
        return self.listVariables('Qubits')


    @setting(98, 'Abort Scan')
    def abort_scan(self, c):
        """Aborts all currently running scans in all contexts"""
        self.abort = True
        

    @setting(99, 'Stats', stats=['w'])
    def stats(self, c, stats):
        """Selects stats"""
        c['Stats'] = stats

        

    @setting(100, 'Squid Steps', region=['(v[mV]{start}, v[mV]{end}, v[mV]{steps})', ''],
                                 returns=['*ss'])
    def squid_steps(self, c, region):
        self.checkSetup(c, 'Squidsteps', 1)

        qname = c['Qubits'][0]
        qubit = self.qubits[qname]
        
        # Setup dataset
        p = self.dataServer.packet(context=c.ID)
        self.add_dataset_setup(p, c['Session'], 'Squid Steps on %s' % qname, ['Flux [mV]'],
                               ['Switching Time (negative) [us]', 'Switching Time (positive) [us]'])
        self.add_qubit_parameters(p, qname)
        p.add_parameter('Stats', float(c['Stats']))
        dataset = (yield p.send()).new # get the dataset name

        # Data handling function
        switchings = {}
        def handleData(results, flux, reset):
            if flux not in switchings:
                # save this until we get the backward switching as well
                switchings[flux] = results.run_experiment[0]
            else:
                # now we have forward and backward switching,
                # so we'll go ahead and add both to the data vault
                d = [[flux, a/25.0, b/25.0]
                      for a, b in zip(switchings[flux], results.run_experiment[0])]
                del switchings[flux]
                # TODO: check to make sure no errors occur here:
                self.dataServer.add(d, context=c.ID)
                

        # Take data
        fluxneg = qubit['Flux Limit Negative']
        fluxpos = qubit['Flux Limit Positive']
        
        self.setupThreading(c)

        fluxmin, fluxmax, fluxstep = getRange(region, fluxneg, fluxpos, 100)
            
        flux = fluxmin
        self.abort = False
        while flux <= fluxmax and not self.abort:
            for reset in [fluxneg, fluxpos]:
                p = self.qubitServer.packet()
                
                p.experiment_new(c['Setup'])
                # Set Biases to Reset, Zero
                p.experiment_send_bias_commands([(('Flux',  1), getCMD(1, reset)),
                                                 (('Squid', 1), getCMD(1, qubit['Squid Zero']))],
                                                T.Value(7.0, 'us'))
                # Select DAC 1 fast for flux and squid
                p.experiment_send_bias_commands([(('Flux',  1), 0x50001),
                                                 (('Squid', 1), 0x50001)],
                                                qubit['Reset Settling Time'])
                # Set Flux bias to Measure
                p.experiment_send_bias_commands([(('Flux',  1), getCMD(1, flux))],
                                                qubit['Measure Settling Time'])
                # Squid Ramp
                add_squid_ramp(p, qubit)
                p.run_experiment(c['Stats'])

                yield self.threadSend(c, handleData, p, flux, reset)
            flux += fluxstep

        yield self.finishThreads(c, handleData)

        returnValue(dataset)


    # Default 1-Qubit data handling function
    def handleSingleQubitData(self, results, cutoffvals, cID, *scanpos):
        total = len(results.run_experiment[0])
        states = [0]*total
        for i, coval in enumerate(cutoffvals):
            statemask = 1 << i
            cutoff = abs(coval)*25
            negate = coval<0      
            for ofs, a in enumerate(results.run_experiment[i]):
                if (a>cutoff) ^ negate:
                    states[ofs] |= statemask
        counts = [0]*((1 << len(cutoffvals))-1)
        for state in states:
            if state > 0:
                counts[state-1] += 1
        d = list(scanpos) + [100.0*c/total for c in counts]
        self.dataServer.add(d, context = cID)



    @setting(110, 'Step Edge', region=['(v[mV]{start}, v[mV]{end}, v[mV]{steps})', ''],
                               returns=['*ss'])
    def step_edge(self, c, region):
        self.checkSetup(c, 'Step Edge', 1)

        qubit = c['Qubits'][0]

        # Setup dataset
        p = self.dataServer.packet(context=c.ID)
        self.add_dataset_setup(p, c['Session'], 'Step Edge on %s' % qubit, ['Flux [mV]'],
                               ['Probability (|1>) [%]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        fluxmin, fluxmax, fluxstep = getRange(region, self.qubits[qubit]['Flux Limit Negative'],
                                                      self.qubits[qubit]['Flux Limit Positive'],
                                                      100)
        cutoffs = [self.qubits[qubit]['1-State Cutoff']]
        flux = fluxmin
        self.abort = False
        while (flux <= fluxmax) and not self.abort:
            p = self.qubitServer.packet()

            p.experiment_new(c['Setup'])
            # Reset Qubit
            add_qubit_resets(p, [self.qubits[qubit]])
            # Go to Operating Bias
            p.experiment_send_bias_commands([(('Flux',  1), getCMD(1, flux))],
                                            self.qubits[qubit]['Bias Settling Time'])
            # Measure
            add_measurement(p, self.qubits[qubit])
            p.run_experiment(c['Stats'])

            yield self.threadSend(c, self.handleSingleQubitData, p, cutoffs, c.ID, flux)
            flux += fluxstep

        yield self.finishThreads(c, self.handleSingleQubitData)

        returnValue(name)



    @setting(120, 'S-Curve', region=['(v[mV]{start}, v[mV]{end}, v[mV]{steps})', ''],
                             returns=['*ss'])
    def s_curve(self, c, region):
        self.checkSetup(c, 'S-Curve', 1)

        qubit = c['Qubits'][0]

        # Setup dataset
        p = self.dataServer.packet(context=c.ID)
        self.add_dataset_setup(p, c['Session'], 'S-Curve on %s' % qubit, ['Measure Pulse Amplitude [mV]'],
                               ['Probability (|1>) [%]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        ampmin, ampmax, ampstep = getRange(region, 0, 1000, 25)

        cutoffs = [self.qubits[qubit]['1-State Cutoff']]
        amp = ampmin
        self.abort = False
        mplen = int(self.qubits[qubit]['Measure Pulse Length'])
        while (amp <= ampmax) and not self.abort:
            p = self.qubitServer.packet()

            p.experiment_new(c['Setup'])
            # Initialize Qubit
            add_qubit_inits(p, [self.qubits[qubit]])
            # Send Measure Pulse
            p.add_analog_data(('Measure', 1), [amp/1000.0]*mplen)
            p.finish_sram_block()
            # Readout
            add_measurement(p, self.qubits[qubit])
            p.run_experiment(c['Stats'])

            yield self.threadSend(c, self.handleSingleQubitData, p, cutoffs, c.ID, amp)
            amp += ampstep

        yield self.finishThreads(c, self.handleSingleQubitData)

        returnValue(name)



    @setting(130, 'Spectroscopy', power=['v[dBm]'], region=['(v[GHz]{start}, v[GHz]{end}, v[MHz]{steps})'],
                                  returns=['*ss'])
    def spectroscopy(self, c, power, region=None):
        self.checkSetup(c, 'Spectroscopy', None)

        arctxts = [self.getMyContext('Anritsu', i) for i in range(len(c['Qubits']))]

        waits = []

        for i, qubit in enumerate(c['Qubits']):
            p = self.anritsuServer.packet(context=arctxts[i])
            p.select_device(int(self.qubits[qubit]['Anritsu ID']))
            p.amplitude(power)
            waits.append(p.send())
            
        yield defer.DeferredList(waits)

        axes  = ['Probability (%s) [%%]' % stname for stname in getStates(len(c['Qubits']))]

        # Setup dataset
        p = self.dataServer.packet(context=c.ID)
        self.add_dataset_setup(p, c['Session'], 'Spectroscopy on %s' % c['Setup'], ['Frequency [GHz]'], axes)
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)
        
        if not(region is None):
            region = list(region)
            region[2] = T.Value(region[2]/1000.0, 'GHz')

        frqmin, frqmax, frqstep = getRange(region, 5, 10, 100)

        cutoffs = [self.qubits[qubit]['1-State Cutoff'] for qubit in c['Qubits']]
        frq = frqmin
        self.abort = False
        mplen = dict((qubit, int(self.qubits[qubit]['Measure Pulse Length'   ]      )) for qubit in c['Qubits'])
        mpamp = dict((qubit,     self.qubits[qubit]['Measure Pulse Amplitude']/1000.0) for qubit in c['Qubits'])
        while (frq < frqmax+(frqstep/3.0)) and not self.abort:
            p = self.qubitServer.packet()
            
            p.experiment_new(c['Setup'])
            # Initialize Qubits
            add_qubit_inits(p, [self.qubits[qubit] for qubit in c['Qubits']])
            for i, qubit in enumerate(c['Qubits']):
                # Send uWave Pulse
                p.add_iq_data     (('uWaves',  i+1), [1]*2000, 6, False)
                # Send Measure Pulse
                p.add_analog_delay(('Measure', i+1), 2000)
                p.add_analog_data (('Measure', i+1), [mpamp[qubit]]*mplen[qubit])
            p.finish_sram_block()
            # Readout
            add_goto_measure_biases(p, [self.qubits[qubit] for qubit in c['Qubits']])
            arsetup = []
            for i, qubit in enumerate(c['Qubits']):
                if i > 0:
                    p.experiment_add_bias_delay(T.Value(200,'us'))
                add_squid_ramp(p, self.qubits[qubit], i+1)
                arsetup.append((arctxts[i], 'Anritsu Server', [('Frequency', T.Value(frq, 'GHz'))]))
            # Set anritsu frequency and run experiment
            p.run_experiment(c['Stats'], arsetup)

            yield self.threadSend(c, self.handleSingleQubitData, p, cutoffs, c.ID, frq)
            frq += frqstep

        yield self.finishThreads(c, self.handleSingleQubitData)
        
        returnValue(name)



    @setting(140, 'Rabi', amplitude=['v[]'], region=['(v[ns]{start}, v[ns]{end}, v[ns]{steps})'],
                          returns=['*ss'])
    def rabi(self, c, amplitude, region = None):
        self.checkSetup(c, 'Rabi', 1)

        qubit = c['Qubits'][0]

        sbmix = self.qubits[qubit]['Sideband Frequency']
        frq = T.Value(self.qubits[qubit]['Resonance Frequency'] - sbmix/1000.0, ' GHz')


        p = self.anritsuServer.packet(context=c.ID)
        p.select_device(int(self.qubits[qubit]['Anritsu ID']))
        p.amplitude(T.Value(2.7,'dBm'))
        p.frequency(frq)
        yield p.send()
            
        # Setup dataset
        p = self.dataServer.packet(context=c.ID)
        self.add_dataset_setup(p, c['Session'], 'Rabi on %s' % qubit, ['Rabi Length [ns]'],
                               ['Probability (|1>) [%]'])
        self.add_qubit_parameters(p, qubit)
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)

        timemin, timemax, timestep = getRange(region, 0, 1000, 1)

        cutoffs = [self.qubits[qubit]['1-State Cutoff']]
        time=timemin
        self.abort = False
        mplen = int(self.qubits[qubit]['Measure Pulse Length'   ])
        mpamp =     self.qubits[qubit]['Measure Pulse Amplitude']/1000.0
        mpofs = int(self.qubits[qubit]['Measure Pulse Offset'   ])
        while (time <= timemax) and not self.abort:
            p = self.qubitServer.packet()

            p.experiment_new(c['Setup'])
            # Initialize Qubit
            add_qubit_inits(p, [self.qubits[qubit]])
            # Add trigger
#            p.add_trigger_pulse(('Trigger', 1), 25)
            # Send uWave Pulse
            p.add_iq_delay           (('uWaves', 1), 200, frq)
            p.add_iq_data_by_envelope(('uWaves', 1), [amplitude]*int(time), frq, sbmix, 0)
            # Send Measure Pulse
            p.add_analog_delay(('Measure', 1), time+mpofs+200)
            p.add_analog_data (('Measure', 1), [mpamp]*mplen)
            p.finish_sram_block()
            # Readout
            add_measurement(p, self.qubits[qubit])
            p.run_experiment(c['Stats'])

            yield self.threadSend(c, self.handleSingleQubitData, p, cutoffs, c.ID, time)
            time += timestep

        yield self.finishThreads(c, self.handleSingleQubitData)

        returnValue(name)



    @setting(150, 'T1', region=['(v[ns]{start}, v[ns]{end}, v[ns]{steps})'],
                        returns=['*ss'])
    def t1(self, c, region = None):
        self.checkSetup(c, 'Spectroscopy', None)

        names = c['Qubits']
        qubits = [self.qubits[name] for name in names]
        both = zip(names, qubits)
        
        # Set Anritsu amplitudes and frequencies
        arctxts = [self.getMyContext('Anritsu', i) for i in range(len(c['Qubits']))]
        waits = []
        for qubit, ctx in zip(qubits, arctxts):
            sbmix = qubit['Sideband Frequency']
            frq = T.Value(qubit['Resonance Frequency'] - sbmix/1000.0, ' GHz')
            p = self.anritsuServer.packet(context=arctxts[i])
            p.select_device(int(qubit['Anritsu ID']))
            p.amplitude(T.Value(2.7,'dBm'))
            p.frequency(frq)
            waits.append(p.send(context=ctx))
        yield defer.DeferredList(waits)

        # Setup dataset
        axes  = ['Probability (%s) [%%]' % stname for stname in getStates(len(c['Qubits']))]
        p = self.dataServer.packet(context=c.ID)
        self.add_dataset_setup(p, c['Session'], 'T1-Sweep on %s' % c['Setup'], ['Frequency [GHz]'], axes)
        self.add_qubit_parameters(p, names[0])
        p.add_parameter('Stats', float(c["Stats"]))
        name = (yield p.send()).new

        # Take data
        self.setupThreading(c)
        
        timemin, timemax, timestep = getRange(region, 0, 1000, 1)

        cutoffs = [qubit['1-State Cutoff'] for qubit in qubits]
        time = timemin
        self.abort = False
        while (time <= timemax) and not self.abort:
            p = self.qubitServer.packet()
            p.experiment_new(c['Setup'])
            
            # Initialize Qubits
            add_qubit_inits(p, qubits)
            
            # Send SRAM
            for i, qubit in enumerate(qubits):
                mpofs = int(qubit['Measure Pulse Offset'   ])
                mplen = int(qubit['Measure Pulse Length'   ])
                mpamp =     qubit['Measure Pulse Amplitude']/1000.0
                pilen = int(qubit['Pi-Pulse Length'        ])
                piamp =     qubit['Pi-Pulse Amplitude'     ]
                sbmix =     qubit['Sideband Frequency'     ]
                rfreq =     qubit['Resonance Frequency'    ]
                # Send uWave Pulse
                p.add_iq_delay           (('uWaves', i+1), 200, rfreq)
                p.add_iq_data_by_envelope(('uWaves', i+1), [piamp]*pilen, rfreq, sbmix, 0)
                # Send Measure Pulse
                p.add_analog_delay(('Measure', i+1), time+mpofs+200)
                p.add_analog_data (('Measure', i+1), [mpamp]*mplen)
            p.finish_sram_block()
            
            # Measure
            add_goto_measure_biases(p, qubits)
            for i, qubit in enumerate(qubits):
                if i > 0:
                    p.experiment_add_bias_delay(T.Value(200,'us'))
                add_squid_ramp(p, qubit, i+1)
            
            # Set anritsu frequency and run experiment
            p.run_experiment(c['Stats'])
            yield self.threadSend(c, self.handleSingleQubitData, p, cutoffs, c.ID, time)
            
            time += timestep

        yield self.finishThreads(c, self.handleSingleQubitData)
        
        returnValue(name)


__server__ = ExperimentServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
