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

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from datetime import datetime

from copy import deepcopy

import struct

import numpy
from scipy.signal import slepian

DEBUG = 0

SRAMPREPAD  = 20
SRAMPOSTPAD = 80

SRAMPAD = SRAMPREPAD + SRAMPOSTPAD

class DeviceNotFoundError(T.Error):
    code = 1
    def __init__(self, name):
        self.msg="Device '%s' not found" % name

class ChannelNotFoundError(T.Error):
    code = 2
    def __init__(self, name):
        self.msg="Channel '%s' not found" % name

class QubitNotFoundError(T.Error):
    code = 3
    def __init__(self, name):
        self.msg="Qubit '%s' is not defined yet" % name

class QubitExistsError(T.Error):
    code = 4
    def __init__(self, name):
        self.msg="Qubit '%s' is already defined" % name

class NoQubitSelectedError(T.Error):
    """No qubit is selected in the current context"""
    code = 5

class SetupNotFoundError(T.Error):
    code = 6
    def __init__(self, name):
        self.msg="Setup '%s' is not defined yet" % name

class ResourceConflictError(T.Error):
    code = 7
    def __init__(self, board, channel):
        self.msg="Resource conflict: Channel '%s' on board '%s' is used multiple times" % (channel, board)

class QubitChannelNotFoundError(T.Error):
    code = 8
    def __init__(self, qubit, channel):
        self.msg="In the current experiment, there is no qubit '%d' with a channel '%s'" % (qubit, channel)

class QubitIndexNotFoundError(T.Error):
    code = 9
    def __init__(self, qubit):
        self.msg="In the current experiment, there is no qubit '%d'" % qubit

class QubitTimerStartedError(T.Error):
    code = 10
    def __init__(self, qubit):
        self.msg="The timer has already been started on qubit '%d'" % qubit

class QubitTimerNotStartedError(T.Error):
    code = 11
    def __init__(self, qubit):
        self.msg="The timer has not yet been started on qubit '%d'" % qubit

class QubitTimerStoppedError(T.Error):
    code = 12
    def __init__(self, qubit):
        self.msg="The timer has already been stopped on qubit '%d'" % qubit

class QubitTimerNotStoppedError(T.Error):
    """The timer needs to be started and stopped on all qubits at least once"""
    code = 13

class SetupExistsError(T.Error):
    code = 14
    def __init__(self, name):
        self.msg="Experimental setup '%s' is already defined" % name

class NoExperimentError(T.Error):
    """No experiment is defined in the current context"""
    code = 15

class AnritsuSetupError(T.Error):
    """I/Q signals need to be corrected for the carrier frequency. Please use 'Experiment Set Anritsu' to setup the microwave generator"""
    code = 16

class AnritsuConflictError(T.Error):
    """Anritsu is already configured with conflicting parameters"""
    code = 17

class QubitChannelNotDeconvolvedError(T.Error):
    code = 18
    def __init__(self, qubit, channel):
        self.msg="Channel '%s' on qubit '%d' does not require deconvolution" % (channel, qubit)
        
class ContextNotFoundError(T.Error):
    code = 19
    def __init__(self, context):
        self.msg="Context (%d, %d) not found" % context



def GrabFromList(element, options, error):
    if isinstance(element, str):
        if not (element in options):
            raise error(element)
        element = options.index(element)
    if (element<0) or (element>=len(options)):
        raise error(element)
    return element, options[element]


class QubitServer(LabradServer):
    """This server abstracts the implementation details of the GHz DACs' functionality as well as the physical wiring to the fridge"""
    name = 'Qubits'

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
        p.cd(['', 'Servers', 'Qubit Server', folder], True)
        p.set(name, repr(variable))
        ans = yield p.send()
        returnValue(ans.set)

    @inlineCallbacks
    def loadVariable(self, folder, name):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Qubit Server', folder], True)
        p.get(name)
        ans = yield p.send()
        data = T.evalLRData(ans.get)
        returnValue(data)

    @inlineCallbacks
    def listVariables(self, folder):
        cxn = self.client
        p = cxn.registry.packet()
        p.cd(['', 'Servers', 'Qubit Server', folder], True)
        p.dir()
        ans = yield p.send()
        returnValue(ans.dir[1])

    @inlineCallbacks
    def initServer(self):
        self.Qubits = {}
        self.Setups = {}
        cxn = self.client
        self.GHzDACs = yield cxn.ghz_dacs.list_devices()
        self.GHzDACs = [d for i, d in self.GHzDACs]
        self.Anritsus = yield cxn.anritsu_server.list_devices()
        self.Anritsus = [d for i, d in self.Anritsus]
        self.DACchannels  = ['DAC A', 'DAC B']
        self.FOchannels   = [ 'FO 0',  'FO 1']
        self.FOcommands   = [0x100000, 0x200000]
        self.Trigchannels = ['S 0', 'S 1', 'S 2', 'S 3']



    @setting(10000, 'Duplicate Context', prototype=['(ww)'])
    def dupe_ctxt(self, c, prototype):
        """Duplicate the settings of the specified context in this context."""
        if prototype[0] == 0:
            prototype = (c.ID[0], prototype[1])
        if prototype not in self.contexts:
            raise ContextNotFoundError(prototype)
        newc = deepcopy(self.contexts[prototype].data)
        for key in c.keys():
            if key not in newc:
                del c[key]
        c.update(newc)
        


    @setting(1, 'List GHzDAC boards', returns=['*(ws)'])
    def list_fpgaboards(self, c):
        """Returns a list of all available GHzDAC boards"""
        return list(enumerate(self.GHzDACs))



    @setting(2, 'List DAC Channels', returns=['*(ws)'])
    def list_dacchannels(self, c):
        """Returns a list of all DAC channels"""
        return list(enumerate(self.DACchannels))



    @setting(3, 'List FO Channels', returns=['*(ws)'])
    def list_fochannels(self, c):
        """Returns a list of all FO channels"""
        return list(enumerate(self.FOchannels))



    @setting(4, 'List Trigger Channels', returns=['*(ws)'])
    def list_trigchannels(self, c):
        """Returns a list of all Trigger channels"""
        return list(enumerate(self.Trigchannels))
        


    @setting(5, 'List Anritsus', returns=['*(ws)'])
    def list_anritsus(self, c):
        """Returns a list of all available Anritsu microwave generators"""
        return list(enumerate(self.Anritsus))



    @setting(20, 'Qubit New', qubit=['s'], timingboard=['w','s'], returns=['s'])
    def add_qubit(self, c, qubit, timingboard):
        """Creates a new Qubit definition"""
        if qubit in self.Qubits:
            raise QubitExistsError(qubit)
        timingboard = GrabFromList(timingboard, self.GHzDACs, DeviceNotFoundError)
        self.Qubits[qubit]={'Timing':   timingboard,
                            'IQs':      {},
                            'Analogs':  {},
                            'FOs':      {},
                            'Triggers': {}}
        c['Qubit']=qubit
        return "%s on %s" % (qubit, timingboard[1])



    @setting(21, 'Qubit Select', qubit=['s'], returns=['s'])
    def select_qubit(self, c, qubit):
        """Selects a Qubit definition for modification"""
        if qubit not in self.Qubits:
            raise QubitNotFoundError(qubit)
        c['Qubit']=qubit
        return qubit



    @setting(22, 'Qubit List', returns=['*s'])
    def list_qubits(self, c):
        """Lists all loaded Qubit definitions"""
        return self.Qubits.keys()



    @setting(23, 'Qubit Delete', qubit=['s'])
    def delete_qubit(self, c, qubit):
        """Deletes a Qubit definition"""
        if qubit not in self.Qubits:
            raise QubitNotFoundError(qubit)
        del self.Qubits[qubit]
        c['Qubit']=''



    @setting(25, 'Qubit Save', qubit=['s'], returns=['s'])
    def save_qubit(self, c, qubit):
        """Saves a Qubit definition to the Registry"""
        if qubit not in self.Qubits:
            raise QubitNotFoundError(qubit)
        yield self.saveVariable('Qubits', qubit, self.Qubits[qubit])
        returnValue(qubit)



    @setting(26, 'Qubit Load', qubit=['s'], returns=['s'])
    def load_qubit(self, c, qubit):
        """Loads a Qubit definition from the Registry"""
        self.Qubits[qubit]=yield self.loadVariable('Qubits', qubit)
        returnValue(repr(self.Qubits[qubit]))



    @setting(27, 'Qubit List Saved', returns=['*s'])
    def list_saved_qubits(self, c):
        """Lists all Qubit definitions saved in the Registry"""
        qubits = yield self.listVariables('Qubits')
        returnValue(qubits)



    @setting(30, 'Qubit Add I/Q Channel', channel_name=['s'], fpgaboard=['w','s'],
                                          anritsu=['w','s'], returns=['s'])
    def add_IQchannel(self, c, channel_name, fpgaboard, anritsu):
        """Adds an analog output channel with IQ mixing capabilities, i.e. a
        channel that plays back complex data"""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.GHzDACs,  DeviceNotFoundError)
        anritsu   = GrabFromList(anritsu,   self.Anritsus, DeviceNotFoundError)
        cQ['IQs'][channel_name]= {'Board': fpgaboard, 'Anritsu': anritsu}
        return 'I/Q on %s connected to %s' % (fpgaboard[1], anritsu[1])



    @setting(31, 'Qubit Add Analog Channel', channel_name=['s'], fpgaboard=['w','s'],
                                             dac=['w','s'], returns=['s'])
    def add_analogchannel(self, c, channel_name, fpgaboard, dac):
        """Adds an analog output channel without IQ mixing capabilities, i.e. a
        channel that plays back real data"""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.GHzDACs, DeviceNotFoundError)
        dac = GrabFromList(dac, self.DACchannels, ChannelNotFoundError)
        cQ['Analogs'][channel_name]= {'Board': fpgaboard,
                                      'DAC':   dac}
        return '%s on %s' % (dac[1], fpgaboard[1])



    @setting(40, 'Qubit Add Digital Channel', channel_name=['s'], fpgaboard=['w','s'],
                                              trigger=['w','s'], returns=['s'])
    def add_digitalchannel(self, c, channel_name, fpgaboard, trigger):
        """Adds a digital output channel (trigger)"""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.GHzDACs, DeviceNotFoundError)
        trigger = GrabFromList(trigger, self.Trigchannels, ChannelNotFoundError)
        cQ['Triggers'][channel_name]= {'Board':   fpgaboard,
                                       'Trigger': trigger}
        return '%s on %s' % (trigger[1], fpgaboard[1])



    @setting(50, 'Qubit Add Bias Channel', channel_name=['s'], fpgaboard=['w','s'],
                                           fo_channel=['w','s'], returns=['s'])
    def add_biaschannel(self, c, channel_name, fpgaboard, fo_channel):
        """Adds a fiber optic bias channel"""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.GHzDACs, DeviceNotFoundError)
        fo_channel = GrabFromList(fo_channel, self.FOchannels, ChannelNotFoundError)
        cQ['FOs'][channel_name]= {'Board': fpgaboard,
                                  'FO':    fo_channel}
        return '%s on %s' % (fo_channel[1], fpgaboard[1])



    @setting(60, 'Setup New', name=['s'], qubits=['*s'], masterFPGAboard=['s','w'],
                              returns=['*(s, *s)*s: List of involved FPGAs and their used channels, list of involved Anritsus'])
    def add_setup(self, c, name, qubits, masterFPGAboard):
        """Creates a new Experimental Setup definition by selecting the involved Qubits and the Master FPGA"""
        if name in self.Setups:
            raise SetupExistsError(name)
        
        masterFPGAboard = GrabFromList(masterFPGAboard, self.GHzDACs, DeviceNotFoundError)
        Resources = {masterFPGAboard[1]: []}
        Anritsus = []
        for qname in qubits:
            q = self.getQubit(qname)
            for i in q['IQs'].values():
                if i['Board'][1] not in Resources:
                    Resources[i['Board'][1]] = []
                for d in self.DACchannels:
                    if d in Resources[i['Board'][1]]:
                        raise ResourceConflictError(i['Board'][1], d)
                Resources[i['Board'][1]].extend(self.DACchannels)
                if i['Anritsu'][1] not in Anritsus:
                    Anritsus.append(i['Anritsu'][1])
                
            for i in q['Analogs'].values():
                if i['Board'][1] not in Resources:
                    Resources[i['Board'][1]] = []
                if (i['DAC'][1]) in Resources[i['Board'][1]]:
                    raise ResourceConflictError(i['Board'][1], i['DAC'][1])
                Resources[i['Board'][1]].append(i['DAC'][1])
                
            for i in q['Triggers'].values():
                if i['Board'][1] not in Resources:
                    Resources[i['Board'][1]] = []
                if (i['Trigger'][1]) in Resources[i['Board'][1]]:
                    raise ResourceConflictError(i['Board'][1], i['Trigger'][1])
                Resources[i['Board'][1]].append(i['Trigger'][1])
                
            for i in q['FOs'].values():
                if i['Board'][1] not in Resources:
                    Resources[i['Board'][1]] = []
                if (i['FO'][1]) in Resources[i['Board'][1]]:
                    raise ResourceConflictError(i['Board'][1], i['FO'][1])
                Resources[i['Board'][1]].append(i['FO'][1])
                    
        self.Setups[name]={'Qubits':   qubits,
                           'Master':   masterFPGAboard[1],
                           'Devices':  Resources,
                           'Anritsus': Anritsus}
        return Resources.items(), Anritsus


    @setting(61, 'Setup List', returns=['*s'])
    def list_setups(self, c):
        """Lists all currently loaded Experimental Setup definitions"""
        return self.Setups.keys()



    @setting(62, 'Setup Delete', name=['s'])
    def delete_setup(self, c, name):
        """Deletes an Experimental Setup"""
        if name not in self.Setups:
            raise SetupNotFoundError(name)
        del self.Setups[name]



    @setting(65, 'Setup Save', name=['s'], returns=['s'])
    def save_setup(self, c, name):
        """Saves an Experimental Setup definition to the Registry"""
        if name not in self.Setups:
            raise SetupNotFoundError(name)
        yield self.saveVariable('Setups', name, self.Setups[name])
        returnValue(name)



    @setting(66, 'Setup Load', name=['s'], returns=['s'])
    def load_setup(self, c, name):
        """Loads an Experimental Setup definition from the Registry"""
        self.Setups[name]=yield self.loadVariable('Setups', name)
        returnValue(repr(self.Setups[name]))



    @setting(67, 'Setup List Saved', returns=['*s'])
    def list_saved_setups(self, c):
        """Lists all Experimental Setups stored in the Registry"""
        setups = yield self.listVariables('Setups')
        returnValue(setups)



    @setting(100, 'Experiment New', setup=['s'], returns=['(*s*(s, w, s))'])
    def new_expt(self, c, setup):
        """Begins a new experiment with the given setup and returns the needed data channels."""
        if setup not in self.Setups:
            raise SetupNotFoundError(setup)
        Result = []
        Setup = self.Setups[setup]
        
        supportfpgas = Setup['Devices'].keys()
        for q in Setup['Qubits']:
            qubit = self.getQubit(q)
            supportfpgas.remove(qubit['Timing'][1])
            
        c['Experiment']={'Setup':         setup,
                         'IQs':           {},
                         'Analogs':       {},
                         'Triggers':      {},
                         'FOs':           {},
                         'FPGAs':         Setup['Devices'].keys(),
                         'Master':        Setup['Master'],
                         'Memory':        dict([(board, [0x000000])
                                                for board in Setup['Devices'].keys()]),
                         'SRAM':          dict([(board, '')
                                                for board in Setup['Devices'].keys()]),
                         'InSRAM':        False,
                         'TimerStarted':  {},
                         'TimerStopped':  {},
                         'NonTimerFPGAs': supportfpgas,
                         'Anritsus':      dict([(anritsu, None)
                                                for anritsu in Setup['Anritsus']]),
                         'NoDeconvolve':  []}

        for qindex, qname in enumerate(Setup['Qubits']):
            q = self.getQubit(qname)
            for ch, info in q['IQs'].items():
                c['Experiment']['IQs'     ][(ch, qindex+1)] = {'Info': info, 'Data': numpy.array( [0+0j]*SRAMPREPAD)}
                Result.append((ch, qindex+1, "IQ channel '%s' on Qubit %d connected to %s" % (ch, qindex+1, info['Anritsu'][1])))
            for ch, info in q['Analogs'].items():
                c['Experiment']['Analogs' ][(ch, qindex+1)] = {'Info': info, 'Data': numpy.array(  [0.0]*SRAMPREPAD)}
                Result.append((ch, qindex+1, "Analog channel '%s' on Qubit %d" % (ch, qindex+1)))
            for ch, info in q['Triggers'].items():
                c['Experiment']['Triggers'][(ch, qindex+1)] = {'Info': info, 'Data': []}
                Result.append((ch, qindex+1, "Trigger channel '%s' on Qubit %d" % (ch, qindex+1)))
            for ch, info in q['FOs'].items():
                fpgaboard = GrabFromList(info['Board'][1], self.GHzDACs, DeviceNotFoundError)
                fo_channel = GrabFromList(info['FO'][1], self.FOchannels, ChannelNotFoundError)
                c['Experiment']['FOs'][(ch, qindex+1)] = {'FPGA': fpgaboard[1],
                                                          'FO':   fo_channel[0]}
                Result.append((ch, qindex+1,
                              "FO channel '%s' on Qubit %d" % (ch, qindex+1)))
        return (Setup['Qubits'], Result)



    @setting(101, 'Experiment Set Anritsu', data=['(sw): Turn Anritsu off',
                                                  '((sw)v[GHz]v[dBm]): Set Anritsu to this frequency and amplitude'],
                                            returns=['b'])
    def set_anritsu(self, c, data):
        """Specifies the Anritsu settings to be used for this experiment for the given channel."""
        if len(data)==3:
            channel, frq, amp = data
            data = (frq, amp)
        else:
            channel = data
            data = None
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['IQs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        anritsu = c['Experiment']['IQs'][channel]['Info']['Anritsu'][1]
        anritsuinfo = c['Experiment']['Anritsus']
        if data is None:
            newInfo = False
        else:
            newInfo = data
        if anritsuinfo[anritsu] is None:
            anritsuinfo[anritsu] = newInfo
        else:
            if not (anritsuinfo[anritsu] == newInfo):
                raise AnritsuConflictError()
        return anritsuinfo!=False


    @setting(102, 'Experiment Turn Off Deconvolution', channels=["(sw): Don't deconvolve this channel",
                                                                 "*(sw): Don't deconvolve these channels"],
                                                       returns=['*(sw)'])
    def dont_deconvolve(self, c, channels):
        """Prevents deconvolution for a given (set of) channel(s)

        NOTES:
        This feature can be used to reduce the overall load on the LabRAD system by reducing packet traffic
        between the Qubit Server and the DAC Calibration Server, for example in a spectroscopy experiment."""
        if 'Experiment' not in c:
            raise NoExperimentError()
        if isinstance(channels, tuple):
            channels = [channels]
        for channel in channels:
            if (channel not in c['Experiment']['IQs']) and (channel not in c['Experiment']['Analogs']):
                if (channel in c['Experiment']['Triggers']) or (channel in c['Experiment']['FOs']):
                    raise QubitChannelNotDeconvolvedError(channel[1], channel[0])
                else:    
                    raise QubitChannelNotFoundError(channel[1], channel[0])
            if channel not in c['Experiment']['NoDeconvolve']:
                c['Experiment']['NoDeconvolve'].append(channel)
        return c['Experiment']['NoDeconvolve']

    @setting(103, 'Experiment Involved Qubits', returns=['*s'])
    def get_qubits(self, c):
        """Returns the list of qubits involved in the current experiment"""
        if 'Experiment' not in c:
            raise NoExperimentError()
        Setup = self.Setups[c['Experiment']['Setup']]
        return Setup['Qubits']

    @setting(105, 'Memory Current', returns=['*(s*w)'])
    def get_mem(self, c):
        """Returns the current Memory data to be uploaded to the involved FPGAs"""
        if 'Experiment' not in c:
            raise NoExperimentError()
        return c['Experiment']['Memory'].items()

    @setting(106, 'Memory Current As Text', returns=['(*s*2s)'])
    def get_mem_text(self, c):
        """Returns the current Memory data to be uploaded to the involved FPGAs as a hex dump"""
        if 'Experiment' not in c:
            raise NoExperimentError()
        dat = []
        fpgas = c['Experiment']['Memory'].keys()
        vals = c['Experiment']['Memory'].values()
        for b in range(len(vals[0])):
            dat.append(["0x%06X" % vals[a][b] for a in range(len(vals))])
        return (fpgas, dat)

    @setting(110, 'Memory Bias Commands', commands=['*((sw)w)'],
                                          delay=['v[us]'],
                                          returns=['v[us]'])
    def send_bias_commands(self, c, commands, delay=T.Value(10, 'us')):
        """Adds bias box commands to the specified channels and delays to all other channels"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        FOs = c['Experiment']['FOs']
        mems = dict([(board, [0x000000]*len(self.FOchannels))
                     for board in c['Experiment']['FPGAs']])

        # insert commands into memories at location given by FO index
        for ch, cmd in commands:
            if ch not in FOs:
                raise QubitChannelNotFoundError(ch[1], ch[0]);
            command = self.FOcommands[FOs[ch]['FO']] + (cmd & 0x0FFFFF)
            mems[FOs[ch]['FPGA']][FOs[ch]['FO']] = command

        # strip out empties
        maxmem=0
        for vals in mems.values():
            try:
                while True:
                    vals.remove(0x000000)
            except:
                pass
            if len(vals)>maxmem:
                maxmem = len(vals)
                
        # make all the same length by padding with NOOPs
        for vals in mems.values():
            vals += [0x000000]*(maxmem - len(vals))

        # figure out how much delay is needed
        delay = max(int(delay.value*25 + 0.9999999999)-maxmem-2, 0)
        realdelay = T.Value((delay+maxmem+2)/25.0, 'us')
        delseq = []
        while delay > 0x0FFFFF:
            delseq.append(0x3FFFFF)
            delay -= 0x0FFFFF
        delseq.append(0x300000+delay)

        # add sequences into memories
        for key, value in c['Experiment']['Memory'].items():
            value.extend(mems[key])
            value.extend(delseq)
        return realdelay



    @setting(111, 'Memory Delay', delay=['v[us]'], returns=['v[us]'])
    def add_bias_delay(self, c, delay):
        """Adds a delay to all channels"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        # figure out how much delay is needed
        delay = max(int(delay.value*25 + 0.9999999999)-2, 0)
        realdelay = T.Value((delay+2)/25.0, 'us')
        delseq = []
        while delay > 0x0FFFFF:
            delseq.append(0x3FFFFF)
            delay -= 0x0FFFFF
        delseq.append(0x300000+delay)

        # add sequences into memories
        for value in c['Experiment']['Memory'].values():
            value.extend(delseq)
        return realdelay



    @setting(112, 'Memory Start Timer', qubits=['*w'], returns=['v[us]'])
    def start_timer(self, c, qubits):
        """Adds a "Start Timer" command to the specified Qubits and NOP commands to all other Qubits"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        Setup = self.Setups[c['Experiment']['Setup']]
        if c['Experiment']['TimerStarted']=={}:
            fpgas = [fpga for fpga in c['Experiment']['NonTimerFPGAs']]
        else:
            fpgas = []
        for q in qubits:
            if (q==0) or (q>len(Setup['Qubits'])):
                raise QubitIndexNotFoundError(q)
            qubit = self.getQubit(Setup['Qubits'][q-1])
            fpga = qubit['Timing'][1]
            if fpga in c['Experiment']['TimerStarted']:
                if fpga in c['Experiment']['TimerStopped']:
                    if c['Experiment']['TimerStopped'][fpga]<c['Experiment']['TimerStarted'][fpga]:
                        raise QubitTimerStartedError(q)
                else:
                    raise QubitTimerStartedError(q)
            fpgas.append(fpga)
            
        for fpga in fpgas:
            if not fpga in c['Experiment']['TimerStarted']:
                c['Experiment']['TimerStarted'][fpga]=1
            else:
                c['Experiment']['TimerStarted'][fpga]+=1

        # add start command into memories
        for key, value in c['Experiment']['Memory'].items():
            if key in fpgas:
                value.append(0x400000)
            else:
                value.append(0x000000)
        return T.Value(1/25.0, 'us')



    @setting(113, 'Memory Stop Timer', qubits=['*w'], returns=['v[us]'])
    def stop_timer(self, c, qubits):
        """Adds a "Stop Timer" command to the specified Qubits and NOP commands to all other Qubits"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        Setup = self.Setups[c['Experiment']['Setup']]
        if c['Experiment']['TimerStopped']=={}:
            fpgas = [fpga for fpga in c['Experiment']['NonTimerFPGAs']]
        else:
            fpgas = []
        for q in qubits:
            if (q==0) or (q>len(Setup['Qubits'])):
                raise QubitIndexNotFoundError(q)
            qubit = self.getQubit(Setup['Qubits'][q-1])
            fpga = qubit['Timing'][1]
            if not (fpga in c['Experiment']['TimerStarted']):
                raise QubitTimerNotStartedError(q)
            if fpga in c['Experiment']['TimerStopped']:
                if c['Experiment']['TimerStopped'][fpga]==c['Experiment']['TimerStarted'][fpga]:
                    raise QubitTimerNotStartedError(q)
            fpgas.append(fpga)

        for fpga in fpgas:
            if not fpga in c['Experiment']['TimerStopped']:
                c['Experiment']['TimerStopped'][fpga]=1
            else:
                c['Experiment']['TimerStopped'][fpga]+=1
            
        # add stop command into memories
        for key, value in c['Experiment']['Memory'].items():
            if key in fpgas:
                value.append(0x400001)
            else:
                value.append(0x000000)
        return T.Value(1/25.0, 'us')


    def getChannel(self, c, channel, chtype):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment'][chtype]:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        return c['Experiment'][chtype][channel]


    @setting(200, 'SRAM IQ Data', channel=['(sw)'], data = ['*(vv)','*c'])
    def add_iq_data(self, c, channel, data):
        """Adds IQ data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        data = data.asarray
        # convert to complex data if it was tuples
        if len(data.shape)==2:
            data = data[:,0] + data[:,1] * 1j
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(201, 'SRAM IQ Delay', channel=['(sw)'], delay=['v[ns]'])
    def add_iq_delay(self, c, channel, delay):
        """Adds a delay in the IQ data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        data = numpy.array([0+0j]*int(delay))
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(202, 'SRAM IQ Envelope', channel=['(sw)'], data = ['*v'], mixfreq=['v[MHz]'], phaseshift=['v[rad]'])
    def add_iq_envelope(self, c, channel, data, mixfreq, phaseshift):
        """Turns the given envelope data into IQ data with the specified Phase and
        Sideband Mixing. The resulting data is added to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        tofs = max(len(chinfo['Data'])-SRAMPOSTPAD, 0)
        data = data.asarray*numpy.exp(-(2.0j*numpy.pi*(numpy.arange(len(data))+tofs))*mixfreq.value/1000.0 + phaseshift.value*1.0j)
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(203, 'SRAM IQ Slepian', channel=['(sw)'], amplitude=['v'], length=['v[ns]'], mixfreq=['v[MHz]'], phaseshift=['v[rad]'])
    def add_iq_slepian(self, c, channel, amplitude, length, mixfreq, phaseshift):
        """Generates IQ data for a Slepian Pulse with the specified Amplitude, Width, Phase and
        Sideband Mixing. The resulting data is added to the specified Channel"""

        length = int(length)
        data = float(amplitude)*slepian(length, 10.0/length)
        chinfo = self.getChannel(c, channel, 'IQs')        
        tofs = max(len(chinfo['Data'])-SRAMPOSTPAD, 0)
        data = data*numpy.exp(-(2.0j*numpy.pi*(numpy.arange(len(data))+tofs))*mixfreq.value/1000.0 + phaseshift.value*1.0j)
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(210, 'SRAM Analog Data', channel=['(sw)'], data=['*v'])
    def add_analog_data(self, c, channel, data):
        """Adds analog data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Analogs')        
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data.asarray))


    @setting(211, 'SRAM Analog Delay', channel=['(sw)'], delay=['v[ns]'])
    def add_analog_delay(self, c, channel, delay):
        """Adds a delay to the analog data of the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Analogs')        
        chinfo['Data'] = numpy.hstack((chinfo['Data'], numpy.array([0.0]*int(delay))))


    @setting(220, 'SRAM Trigger Pulse', channel=['(sw)'], length=['v[ns]'], returns=['w'])
    def add_trigger_pulse(self, c, channel, length):
        """Adds a Trigger Pulse of the given length to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Triggers')        
        n = int(length.value)
        if n>0:
            chinfo['Data'].append((True, n))
        return n


    @setting(221, 'SRAM Trigger Delay', channel=['(sw)'], length=['v[ns]'], returns=['w'])
    def add_trigger_delay(self, c, channel, length):
        """Adds a delay of the given length to the specified Trigger Channel"""
        chinfo = self.getChannel(c, channel, 'Triggers')        
        n = int(length.value)
        if n>0:
            chinfo['Data'].append((False, n))
        return n


    @inlineCallbacks
    def buildSRAM(self, expt):
        # Get client connection
        cxn = self.client
        
        # Figure out longest SRAM block
        longest = 24
        for chname in ['IQs', 'Analogs', 'Triggers']:
            for ch in expt[chname].keys():
                l = len(expt[chname][ch]['Data'])+SRAMPOSTPAD
                if l>longest:
                    longest = l
        # make sure SRAM length is divisible by 4
        longest = (longest + 3) & 0xFFFFFC
        srams = dict([(board, numpy.zeros(longest).astype('int')) for board in expt['FPGAs']])

        # deconvolve the IQ and Analog channels
        deconvolved = {}
        for chname in ['IQs', 'Analogs']:
            for ch in expt[chname].keys():
                if ch in expt['NoDeconvolve']:
                    d = numpy.hstack((expt[chname][ch]['Data'], numpy.zeros(SRAMPOSTPAD)))
                    if chname=='IQs':
                        d =  ((d.real*0x1FFF).astype('int') & 0x3FFF) + \
                            (((d.imag*0x1FFF).astype('int') & 0x3FFF) << 14)
                    else:                            
                        d =  ((d*0x1FFF).astype('int') & 0x3FFF)
                    deconvolved[(chname, ch)] = d
                    continue
                board = expt[chname][ch]['Info']['Board'][1]
                p = cxn.dac_calibration.packet()
                p.board(board)
                if expt[chname][ch]['Info'].has_key('Anritsu'):
                    anritsu = expt[chname][ch]['Info']['Anritsu'][1]
                    frq = expt['Anritsus'][anritsu]
                    if frq is None:
                        d = numpy.hstack((expt[chname][ch]['Data'], numpy.zeros(SRAMPOSTPAD)))
                        d =  ((d.real*0x1FFF).astype('int') & 0x3FFF) + \
                            (((d.imag*0x1FFF).astype('int') & 0x3FFF) << 14)
                        deconvolved[(chname, ch)] = d
                        continue
                    frq = frq[0]
                    p.frequency(frq)
                else:
                    dac = expt[chname][ch]['Info']['DAC'][1]
                    p.dac(dac)
                p.correct(numpy.hstack((expt[chname][ch]['Data'], numpy.zeros(SRAMPOSTPAD))))
                ans = yield p.send()
                d = ans.correct
                if isinstance(d, tuple):
                    d = ((d[1].asarray & 0x3FFF) << 14) + (d[0].asarray & 0x3FFF)
                else:
                    d = d.asarray & 0x3FFF
                deconvolved[(chname, ch)] = d

        # plug data into srams
        for ch, info in expt['IQs'].items():
            l = len(deconvolved[('IQs', ch)])
            if l>0:
                srams[info['Info']['Board'][1]][0:l]       |=  deconvolved[('IQs', ch)]
                srams[info['Info']['Board'][1]][l:longest] |= [deconvolved[('IQs', ch)][0]] * (longest-l)
            
        for ch, info in expt['Analogs'].items():
            shift = info['Info']['DAC'][0]*14
            l = len(deconvolved[('Analogs', ch)])
            if l>0:
                srams[info['Info']['Board'][1]][0:l]       |=  deconvolved[('Analogs', ch)]    << shift
                srams[info['Info']['Board'][1]][l:longest] |= [deconvolved[('Analogs', ch)][0] << shift] * (longest-l)

        for info in expt['Triggers'].values():
            mask = 1 << (info['Info']['Trigger'][0] + 28)
            ofs = SRAMPREPAD
            for val, count in info['Data']:
                if val:
                    srams[info['Info']['Board'][1]][ofs: ofs+count] |= mask
                ofs += count

        returnValue(srams)


    @setting(230, 'SRAM Plot', session=['*s'], name='s', correct=['b'], returns=[])
    def plot_sram(self, c, session, name, correct=True):
        cxn = self.client
        dv  = cxn.data_vault
        p   = dv.packet()
        yaxes = []
        for ch, qb in sorted(c['Experiment']['IQs'     ].keys()):
            yaxes.append(('Amplitude', "Real part of IQ channel '%s' on Qubit %d" % (ch, qb), "a.u."))
            yaxes.append(('Amplitude', "Imag part of IQ channel '%s' on Qubit %d" % (ch, qb), "a.u."))
        for ch, qb in sorted(c['Experiment']['Analogs' ].keys()):
            yaxes.append(('Amplitude', "Analog channel '%s' on Qubit %d" % (ch, qb), "a.u."))
        for ch, qb in sorted(c['Experiment']['Triggers'].keys()):
            yaxes.append(('Amplitude', "Trigger channel '%s' on Qubit %d" % (ch, qb), "a.u."))
        dir = ['']+session.aslist
        p.cd(dir)
        p.new(name, [('Time', 'ns')], yaxes)
        yield p.send()

        if correct:
            # Build deconvolved SRAM content
            srams = yield self.buildSRAM(c['Experiment'])
            # Extract corrected data from SRAM
            data = None
            for ch, info in sorted(c['Experiment']['IQs'].items()):
                i  = (srams[info['Info']['Board'][1]]      ) & 0x00003FFF
                q  = (srams[info['Info']['Board'][1]] >> 14) & 0x00003FFF
                i-= ((i & 8192) >> 13) * 16384
                q-= ((q & 8192) >> 13) * 16384
                i = i.astype('float')/8192.0
                q = q.astype('float')/8192.0
                if data is None:
                    data = numpy.vstack((numpy.arange(0.0, float(len(i)), 1.0), i, q))
                else:
                    data = numpy.vstack((data, i, q))
                
            for ch, info in sorted(c['Experiment']['Analogs'].items()):
                shift = info['Info']['DAC'][0]*14
                d  = (srams[info['Info']['Board'][1]] >> shift) & 0x00003FFF
                d -= ((d & 8192) >> 13) * 16384
                d = d.astype('float')/8192.0
                if data is None:
                    data = numpy.vstack((range(len(i)), d))
                else:
                    data = numpy.vstack((data, d))

            for ch, info in sorted(c['Experiment']['Triggers'].items()):
                shift = info['Info']['Trigger'][0] + 28
                d  = (srams[info['Info']['Board'][1]] >> shift) & 0x00000001
                d.astype('float')
                if data is None:
                    data = numpy.vstack((range(len(i)), d))
                else:
                    data = numpy.vstack((data, d))
            # Plot
            data = numpy.transpose(data)
            yield dv.add(data)
        else:
            done = False
            t=0
            curtrigs = {}
            while not done:
                done = True
                data = [float(t)]
                for ch in sorted(c['Experiment']['IQs'].keys()):
                    if len(c['Experiment']['IQs'][ch]['Data'])>t:
                        data.append(c['Experiment']['IQs'][ch]['Data'][t].real)
                        data.append(c['Experiment']['IQs'][ch]['Data'][t].imag)
                        done = False
                    else:
                        data.extend([0.0, 0.0])
                for ch in sorted(c['Experiment']['Analogs'].keys()):
                    if len(c['Experiment']['Analogs'][ch]['Data'])>t:
                        data.append(c['Experiment']['Analogs'][ch]['Data'][t])
                        done = False
                    else:
                        data.append(0.0)
                if t<SRAMPREPAD:
                    for ch in sorted(c['Experiment']['Triggers'].keys()):
                        data.append(0.0)
                    done = False
                else:
                    for ch in sorted(c['Experiment']['Triggers'].keys()):
                        if not curtrigs.has_key(ch):
                            curtrigs[ch]=[-1, 0, False]
                        while (not (curtrigs[ch] is None)) and (curtrigs[ch][1]<=0):
                            curtrigs[ch][0]+=1
                            if curtrigs[ch][0]>=len(c['Experiment']['Triggers'][ch]['Data']):
                                curtrigs[ch]=None
                            else:
                                curtrigs[ch][2], curtrigs[ch][1] = c['Experiment']['Triggers'][ch]['Data'][curtrigs[ch][0]]
                        if curtrigs[ch] is None:
                            data.append(0.0)
                        else:
                            curtrigs[ch][1]-=1
                            if curtrigs[ch][2]:
                                data.append(1.0)
                            else:    
                                data.append(0.0)
                            done = False
                if not done:
                    yield dv.add(data)
                t += 1
      
      
    @setting(299, 'Memory Call SRAM', returns=['*s'])
    def finish_sram(self, c):
        """Constructs the final SRAM data from all the Channel data and adds the right
        "Call SRAM" command into the Memory of all Qubits to execute the SRAM data"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        # build deconvolved SRAM content
        srams = yield self.buildSRAM(c['Experiment'])
        
        # add new data onto SRAM
        for board, data in srams.items():
            startaddr = len(c['Experiment']['SRAM'][board])/4
            c['Experiment']['SRAM'][board] += data.tostring()
            endaddr = len(c['Experiment']['SRAM'][board])/4 - 1

        # clear current sram
        for info in c['Experiment']['IQs'].values():
            info['Data'] = numpy.array( [0+0j]*SRAMPREPAD)
        for info in c['Experiment']['Analogs'].values():
            info['Data'] = numpy.array(  [0.0]*SRAMPREPAD)
        for info in c['Experiment']['Triggers'].values():
            info['Data'] = []

        # add call command into memories
        callsram = [0x800000 + (startaddr & 0x0FFFFF),
                    0xA00000 + (  endaddr & 0x0FFFFF),
                    0xC00000]
        for value in c['Experiment']['Memory'].values():
            value.extend(callsram)

        returnValue(srams.keys())
    
    @setting(1000, 'Run', stats=['w'],
                          setuppkts=['*((ww){context}, s{server}, ?{((s?)(s?)(s?)...)})'],
                          returns=['*2w'])
    def run_experiment(self, c, stats, setuppkts=None):
        """Runs the experiment and returns the raw switching data"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        fpgas = [fpga for fpga in c['Experiment']['FPGAs']]
        for fpga in fpgas:
            if fpga in c['Experiment']['TimerStarted']:
                if fpga in c['Experiment']['TimerStopped']:
                    if c['Experiment']['TimerStopped'][fpga]<c['Experiment']['TimerStarted'][fpga]:
                        raise QubitTimerNotStoppedError(q)
                else:
                    raise QubitTimerNotStoppedError(q)
            else:
                QubitTimerNotStoppedError(q)

        cxn = self.client

        setupState=[]

        if len(c['Experiment']['Anritsus'])>0:
            pkt = []
            for anritsu, settings in c['Experiment']['Anritsus'].items():
                pkt.append(('Select Device', anritsu))
                if isinstance(settings, tuple):
                    pkt.append(('Output', True))
                    pkt.append(('Frequency', settings[0]))
                    pkt.append(('Amplitude', settings[1]))
                    setupState.append(anritsu+': '+str(settings[0])+'@'+str(settings[1]))
                else:
                    pkt.append(('Output', False))
                    setupState.append(anritsu+': off')
            if setuppkts is None:
                setuppkts=[]
            setuppkts.append(((long(cxn._cxn.ID), 1L), 'Anritsu Server', tuple(pkt)))
        else:
            setupState=['don''t care']

        for value in c['Experiment']['Memory'].values():
            value.append(0xF00000)

        p = cxn.ghz_dacs.packet(context = c.ID)
        for index, fpga in enumerate(fpgas):
            p.select_device(fpga)
            if len(c['Experiment']['SRAM'][fpga])>0:
                p.sram_address(0)
                p.sram(c['Experiment']['SRAM'][fpga])
            p.memory(c['Experiment']['Memory'][fpga])

        fpgas.remove(c['Experiment']['Master'])
        fpgas = [c['Experiment']['Master']] + fpgas
        p.daisy_chain(fpgas)
        p.timing_order([self.getQubit(qname)['Timing'][1] for qname in self.Setups[c['Experiment']['Setup']]['Qubits']])
        p.start_delay([0]*len(fpgas))
        if setuppkts is None:
            p.run_sequence(stats)
        else:
            p.run_sequence(stats, True, setuppkts, setupState)
        answer = yield p.send()
        timing_data = answer.run_sequence.asarray
        returnValue(timing_data)
        
    @setting(1001, 'Run Without Anritsu', stats=['w'],
                          setuppkts=['*((ww){context}, s{server}, ?{((s?)(s?)(s?)...)})'],
                          setupState=['*s'],
                          returns=['*2w'])
    def run_experiment_without_anritsu(self, c, stats, setuppkts=None, setupState=[]):
        """Runs the experiment and returns the raw switching data"""
        if 'Experiment' not in c:
            raise NoExperimentError()

        fpgas = [fpga for fpga in c['Experiment']['FPGAs']]
        for fpga in fpgas:
            if fpga in c['Experiment']['TimerStarted']:
                if fpga in c['Experiment']['TimerStopped']:
                    if c['Experiment']['TimerStopped'][fpga]<c['Experiment']['TimerStarted'][fpga]:
                        raise QubitTimerNotStoppedError(q)
                else:
                    raise QubitTimerNotStoppedError(q)
            else:
                QubitTimerNotStoppedError(q)

        cxn = self.client

        for value in c['Experiment']['Memory'].values():
            value.append(0xF00000)

        p = cxn.ghz_dacs.packet(context = c.ID)
        for index, fpga in enumerate(fpgas):
            p.select_device(fpga)
            if len(c['Experiment']['SRAM'][fpga])>0:
                p.sram_address(0)
                p.sram(c['Experiment']['SRAM'][fpga])
            p.memory(c['Experiment']['Memory'][fpga])

        fpgas.remove(c['Experiment']['Master'])
        fpgas = [c['Experiment']['Master']] + fpgas
        p.daisy_chain(fpgas)
        p.timing_order([self.getQubit(qname)['Timing'][1] for qname in self.Setups[c['Experiment']['Setup']]['Qubits']])
        p.start_delay([0]*len(fpgas))
        if setuppkts is None:
            p.run_sequence(stats)
        else:
            p.run_sequence(stats, True, setuppkts, setupState)
        answer = yield p.send()
        timing_data = answer.run_sequence.asarray
        returnValue(timing_data)

__server__ = QubitServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
