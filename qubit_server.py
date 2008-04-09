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
    """The timer needs to be started and stopped on all qubits"""
    code = 13

class SetupExistsError(T.Error):
    code = 14
    def __init__(self, name):
        self.msg="Experimental setup '%s' is already defined" % name

class NoExperimentError(T.Error):
    """No experiment is defined in the current context"""
    code = 15


def GrabFromList(element, options, error):
    if isinstance(element, str):
        if not (element in options):
            raise error(element)
        element = options.index(element)
    if (element<0) or (element>=len(options)):
        raise error(element)
    return element, options[element]


class QubitServer(LabradServer):
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
        self.devices = yield cxn.ghz_dacs.list_devices()
        self.devices = [d for i, d in self.devices]
        self.DACchannels  = ['DAC A', 'DAC B']
        self.FOchannels   = [ 'FO 0',  'FO 1']
        self.FOcommands   = [0x100000, 0x200000]
        self.Trigchannels = ['S 0', 'S 1', 'S 2', 'S 3']
        


    @setting(1, 'List FPGA boards', returns=['*(ws)'])
    def list_fpgaboards(self, c):
        return list(enumerate(self.devices))



    @setting(2, 'List DAC Channels', returns=['*(ws)'])
    def list_dacchannels(self, c):
        return list(enumerate(self.DACchannels))



    @setting(3, 'List FO Channels', returns=['*(ws)'])
    def list_fochannels(self, c):
        return list(enumerate(self.FOchannels))



    @setting(4, 'List Trigger Channels', returns=['*(ws)'])
    def list_trigchannels(self, c):
        return list(enumerate(self.Trigchannels))



    @setting(10, 'Save Context', name=['s'], returns=['s'])
    def save_ctxt(self, c, name):
        fname = yield self.saveVariable('Contexts', name, c)
        returnValue(fname)



    @setting(11, 'Load Context', name=['s'], returns=['s'])
    def load_ctxt(self, c, name):
        data = yield self.loadVariable('Contexts', name, c)
        c.update(data)
        returnValue(repr(c))



    @setting(12, 'List Saved Contexts', returns=['*s'])
    def list_ctxts(self, c):
        data = yield self.listVariables('Contexts')
        returnValue(data)



    @setting(20, 'Qubit New', qubit=['s'], timingboard=['w','s'], returns=['s'])
    def add_qubit(self, c, qubit, timingboard):
        if qubit in self.Qubits:
            raise QubitExistsError(qubit)
        timingboard = GrabFromList(timingboard, self.devices, DeviceNotFoundError)
        self.Qubits[qubit]={'Timing':  timingboard,
                            'IQs':      {},
                            'Analogs':  {},
                            'FOs':      {},
                            'Triggers': {}}
        c['Qubit']=qubit
        return "%s on %s" % (qubit, timingboard[1])



    @setting(21, 'Qubit Select', qubit=['s'], returns=['s'])
    def select_qubit(self, c, qubit):
        if qubit not in self.Qubits:
            raise QubitNotFoundError(qubit)
        c['Qubit']=qubit
        return qubit



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
        self.Qubits[qubit]=yield self.loadVariable('Qubits', qubit)
        returnValue(repr(self.Qubits[qubit]))



    @setting(27, 'List Saved Qubits', returns=['*s'])
    def list_saved_qubits(self, c):
        qubits = yield self.listVariables('Qubits')
        returnValue(qubits)



    @setting(30, 'Qubit Add I/Q Channel', channel_name=['s'], fpgaboard=['w','s'],
                                          returns=['s'])
    def add_IQchannel(self, c, channel_name, fpgaboard):
        """Adds an analog output channel with IQ mixing capabilities, i.e. a
        channel that plays back complex data."""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.devices, DeviceNotFoundError)
        cQ['IQs'][channel_name]= {'Board': fpgaboard}
        return 'I/Q on %s' % fpgaboard[1]



    @setting(31, 'Qubit Add Analog Channel', channel_name=['s'], fpgaboard=['w','s'],
                                             dac=['w','s'], returns=['s'])
    def add_analogchannel(self, c, channel_name, fpgaboard, dac):
        """Adds an analog output channel without IQ mixing capabilities, i.e. a
        channel that plays back real data."""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.devices, DeviceNotFoundError)
        dac = GrabFromList(dac, self.DACchannels, ChannelNotFoundError)
        cQ['Analogs'][channel_name]= {'Board': fpgaboard,
                                      'DAC':   dac}
        return '%s on %s' % (dac[1], fpgaboard[1])



    @setting(40, 'Qubit Add Digital Channel', channel_name=['s'], fpgaboard=['w','s'],
                                              trigger=['w','s'], returns=['s'])
    def add_digitalchannel(self, c, channel_name, fpgaboard, trigger):
        """Adds a digital output channel (trigger)."""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.devices, DeviceNotFoundError)
        trigger = GrabFromList(trigger, self.Trigchannels, ChannelNotFoundError)
        cQ['Triggers'][channel_name]= {'Board':   fpgaboard,
                                       'Trigger': trigger}
        return '%s on %s' % (trigger[1], fpgaboard[1])



    @setting(50, 'Qubit Add Bias Channel', channel_name=['s'], fpgaboard=['w','s'],
                                           fo_channel=['w','s'], returns=['s'])
    def add_biaschannel(self, c, channel_name, fpgaboard, fo_channel):
        """Adds a fiber optic bias channel."""
        cQ = self.curQubit(c)
        fpgaboard = GrabFromList(fpgaboard, self.devices, DeviceNotFoundError)
        fo_channel = GrabFromList(fo_channel, self.FOchannels, ChannelNotFoundError)
        cQ['FOs'][channel_name]= {'Board': fpgaboard,
                                  'FO':    fo_channel}
        return '%s on %s' % (fo_channel[1], fpgaboard[1])



    @setting(60, 'Experimental Setup New', name=['s'], qubits=['*s'],
                                           masterFPGAboard=['s','w'],
                                           returns=['*(s, *s): List of involved FPGAs and their used channels'])
    def add_setup(self, c, name, qubits, masterFPGAboard):
        """Selects the qubits involved in an experimental setup."""
        if name in self.Setups:
            raise SetupExistsError(name)
        
        masterFPGAboard = GrabFromList(masterFPGAboard, self.devices, DeviceNotFoundError)
        Resources = {masterFPGAboard[1]: []}
        for qname in qubits:
            q = self.getQubit(qname)
            for i in q['IQs'].values():
                if i['Board'][1] not in Resources:
                    Resources[i['Board'][1]] = []
                for d in self.DACchannels:
                    if d in Resources[i['Board'][1]]:
                        raise ResourceConflictError(i['Board'][1], d)
                Resources[i['Board'][1]].extend(self.DACchannels)
                
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
                    
        self.Setups[name]={'Qubits':  qubits,
                           'Master':  masterFPGAboard[1],
                           'Devices': Resources}
        return Resources.items()



    @setting(61, 'List Experimental Setups', returns=['*s'])
    def list_setups(self, c):
        return self.Setups.keys()



    @setting(65, 'Experimental Setup Save', name=['s'], returns=['s'])
    def save_setup(self, c, name):
        if name not in self.Setups:
            raise SetupNotFoundError(name)
        yield self.saveVariable('Setups', name, self.Setups[name])
        returnValue(name)



    @setting(66, 'Experimental Setup Load', name=['s'], returns=['s'])
    def load_setup(self, c, name):
        self.Setups[name]=yield self.loadVariable('Setups', name)
        returnValue(repr(self.Setups[name]))



    @setting(67, 'List Saved Experimental Setups', returns=['*s'])
    def list_saved_setups(self, c):
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
            
        c['Experiment']={'Setup':    setup,
                         'IQs':      {},
                         'Analogs':  {},
                         'Triggers': {},
                         'FOs':      {},
                         'FPGAs':    Setup['Devices'].keys(),
                         'Master':   Setup['Master'],
                         'Memory':   dict([(board, [0x000000])
                                           for board in Setup['Devices'].keys()]),
                         'SRAM':     dict([(board, '')
                                           for board in Setup['Devices'].keys()]),
                         'InSRAM':   False,
                         'TimerStarted':  [],
                         'TimerStopped':  [],
                         'NonTimerFPGAs': supportfpgas}

        for qindex, qname in enumerate(Setup['Qubits']):
            q = self.getQubit(qname)
            for ch, info in q['IQs'].items():
                c['Experiment']['IQs'][(ch, qindex+1)] = {'Info': info,
                                                          'Data': ([],[])}
                Result.append((ch, qindex+1,
                              "IQ channel '%s' on Qubit %d" % (ch, qindex+1)))
            for ChName in ['Analog', 'Trigger']:
                for ch, info in q[ChName+'s'].items():
                    c['Experiment'][ChName+'s'][(ch, qindex+1)] = {'Info': info,
                                                                   'Data': []}
                    Result.append((ch, qindex+1,
                                  "%s channel '%s' on Qubit %d" %
                                  (ChName,     ch,          qindex+1)))
            for ch, info in q['FOs'].items():
                fpgaboard = GrabFromList(info['Board'][1], self.devices, DeviceNotFoundError)
                fo_channel = GrabFromList(info['FO'][1], self.FOchannels, ChannelNotFoundError)
                c['Experiment']['FOs'][(ch, qindex+1)] = {'FPGA': fpgaboard[1],
                                                          'FO':   fo_channel[0]}
                Result.append((ch, qindex+1,
                              "FO channel '%s' on Qubit %d" % (ch, qindex+1)))
        return (Setup['Qubits'], Result)



    @setting(105, 'Current Memory ', returns=['*(s*w)'])
    def get_mem(self, c):
        if 'Experiment' not in c:
            raise NoExperimentError()
        return c['Experiment']['Memory'].items()

    @setting(106, 'Current Memory As Text', returns=['(*s*2s)'])
    def get_mem_text(self, c):
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
        if 'Experiment' not in c:
            raise NoExperimentError()

        Setup = self.Setups[c['Experiment']['Setup']]
        if c['Experiment']['TimerStarted']==[]:
            fpgas = [fpga for fpga in c['Experiment']['NonTimerFPGAs']]
        else:
            fpgas = []
        for q in qubits:
            if (q==0) or (q>len(Setup['Qubits'])):
                raise QubitIndexNotFoundError(q)
            qubit = self.getQubit(Setup['Qubits'][q-1])
            fpga = qubit['Timing'][1]
            if fpga in c['Experiment']['TimerStarted']:
                raise QubitTimerStartedError(q)
            fpgas.append(fpga)
            
        for fpga in fpgas:
            c['Experiment']['TimerStarted'].append(fpga)

        # add start command into memories
        for key, value in c['Experiment']['Memory'].items():
            if key in fpgas:
                value.append(0x400000)
            else:
                value.append(0x000000)
        return T.Value(1/25.0, 'us')



    @setting(113, 'Memory Stop Timer', qubits=['*w'], returns=['v[us]'])
    def stop_timer(self, c, qubits):
        if 'Experiment' not in c:
            raise NoExperimentError()

        Setup = self.Setups[c['Experiment']['Setup']]
        if c['Experiment']['TimerStopped']==[]:
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
                raise QubitTimerStoppedError(q)
            fpgas.append(fpga)

        for fpga in fpgas:
            c['Experiment']['TimerStopped'].append(fpga)
            
        # add stop command into memories
        for key, value in c['Experiment']['Memory'].items():
            if key in fpgas:
                value.append(0x400001)
            else:
                value.append(0x000000)
        return T.Value(1/25.0, 'us')


    @inlineCallbacks
    def insertIQData(self, correct, cxn, cID, chinfo, carrierfrq, data):
        if correct:
            p = cxn.dac_calibration.packet(context = cID)
            p.board    (chinfo['Info']['Board'][1])
            p.frequency(carrierfrq)
            p.correct([0])
            p.correct(data)
            deconv = yield p.send()
            zerodata = deconv.correct[0]
            cordata  = deconv.correct[1]
            cordata  = (numpy.array(cordata[0]), numpy.array(cordata[1]))
        else:
            zerodata = ([0],[0])
            if isinstance(data[0], tuple):
                cordata = (numpy.array([0]*len(data)),numpy.array([0]*len(data)))
                for ofs,i,q in enumerate(data):
                    cordata[0][ofs] = i.value*0x1FFF
                    cordata[1][ofs] = q.value*0x1FFF
            else:
                data = numpy.array(data)
                cordata=((data.real*0x1FFF).astype(int),
                         (data.imag*0x1FFF).astype(int))
            
        if len(chinfo['Data'][0])==0:
            chinfo['Data']=(numpy.array(cordata[0]), numpy.array(cordata[1]))
        else:
            chinfo['Data'][0][-SRAMPAD:] += cordata[0][0:SRAMPAD] - zerodata[0][0]
            chinfo['Data'][1][-SRAMPAD:] += cordata[1][0:SRAMPAD] - zerodata[1][0]
            chinfo['Data'] = (numpy.hstack((chinfo['Data'][0], cordata[0][SRAMPAD:])),
                              numpy.hstack((chinfo['Data'][1], cordata[1][SRAMPAD:])))
        chinfo['Data'][0][0:4]=zerodata[0]*4
        chinfo['Data'][1][0:4]=zerodata[1]*4


    @setting(200, 'SRAM IQ Data', channel=['(sw)'], data = ['*(vv)','*c'],
                                  carrierfrq=['v[GHz]'], correct=['b'])
    def add_iq_data(self, c, channel, data, carrierfrq, correct=True):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['IQs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)

        if len(data)>0:
            if isinstance(data[0], tuple):
                data = [(0,0)]*SRAMPREPAD + data + [(0,0)]*SRAMPOSTPAD
            else:
                data = [0]*SRAMPREPAD + data + [0]*SRAMPOSTPAD
        else:
            data = [0]*(SRAMPREPAD+SRAMPOSTPAD)

        yield self.insertIQData(correct, self.client, c.ID,
                                c['Experiment']['IQs'][channel], carrierfrq, data)



    @setting(201, 'SRAM IQ Delay', channel=['(sw)'], delay=['v[ns]'],
                                   carrierfrq=['v[GHz]'], correct=['b'])
    def add_iq_delay(self, c, channel, delay, carrierfrq, correct=True):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['IQs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['IQs'][channel]

        if correct:
            cxn = self.client
            p = cxn.dac_calibration.packet(context = c.ID)
            p.board    (chinfo['Info']['Board'][1])
            p.frequency(carrierfrq)
            p.correct  ([0])
            zerodata = (yield p.send()).correct
        else:
            zerodata = ([0],[0])
        chinfo['Data'] = (numpy.hstack((chinfo['Data'][0], zerodata[0]*int(delay.value))),
                          numpy.hstack((chinfo['Data'][1], zerodata[1]*int(delay.value))))


    @setting(202, 'SRAM IQ Envelope', channel=['(sw)'], data = ['*v'],
                                      carrierfrq=['v[GHz]'], mixfreq=['v[MHz]'],
                                      phaseshift=['v[rad]'], correct=['b'])
    def add_iq_envelope(self, c, channel, data, carrierfrq, mixfreq, phaseshift, correct=True):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['IQs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['IQs'][channel]

        if len(data)>0:
            tofs = max(len(chinfo['Data'][0])-SRAMPOSTPAD, 0)
            data = numpy.array(data)*numpy.exp(-(2.0j*numpy.pi*(numpy.arange(len(data))+tofs) + phaseshift.value)*mixfreq.value/1000.0)
            data = [0]*SRAMPREPAD + data.tolist() + [0]*SRAMPOSTPAD
        else:
            data = [0]*(SRAMPREPAD+SRAMPOSTPAD)

        yield self.insertIQData(correct, self.client, c.ID, chinfo, carrierfrq, data)

    @setting(203, 'SRAM IQ Slepian', channel=['(sw)'],
                                     amplitude=['v'], length=['v[ns]'],
                                     carrierfrq=['v[GHz]'], mixfreq=['v[MHz]'],
                                     phaseshift=['v[rad]'], correct=['b'])
    def add_iq_slepian(self, c, channel, amplitude, length, carrierfrq, mixfreq, phaseshift, correct=True):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['IQs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['IQs'][channel]

        length = int(length)
        data = amplitude*slepian(length, 10.0/length)

        if len(data)>0:
            tofs = max(len(chinfo['Data'][0])-SRAMPOSTPAD, 0)
            data = numpy.array(data)*numpy.exp(-(2.0j*numpy.pi*(numpy.arange(len(data))+tofs) + phaseshift.value)*mixfreq.value/1000.0)
            data = [0]*SRAMPREPAD + data.tolist() + [0]*SRAMPOSTPAD
        else:
            data = [0]*(SRAMPREPAD+SRAMPOSTPAD)

        yield self.insertIQData(correct, self.client, c.ID, chinfo, carrierfrq, data)


    @setting(210, 'SRAM Analog Data', channel=['(sw)'], data=['*v'], correct=['b'])
    def add_analog_data(self, c, channel, data, correct=True):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['Analogs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['Analogs'][channel]

        if correct:
            cxn = self.client
            p = cxn.dac_calibration.packet(context = c.ID)
            p.board(chinfo['Info']['Board'][1])
            p.dac  (chinfo['Info']['DAC'][1])
            p.correct([0])
            p.correct(numpy.hstack((numpy.zeros(SRAMPREPAD),
                                    data.asarray,
                                    numpy.zeros(SRAMPOSTPAD))))
            #p.correct([0]*SRAMPREPAD + data.aslist + [0]*SRAMPOSTPAD)
            deconv = yield p.send()
            zerodata = deconv.correct[0].asarray[0]
            cordata  = deconv.correct[1].asarray
        else:
            zerodata = 0
            cordata = numpy.array([0]*(SRAMPREPAD+len(data)+SRAMPOSTPAD))
            cordata[SRAMPREPAD:SRAMPREPAD+len(data)]=(numpy.array(data)*0x1FFF).astype(int)

        if len(chinfo['Data'])==0:
            chinfo['Data']=cordata
        else:
            chinfo['Data'][-SRAMPAD:] += (cordata[0:SRAMPAD] - zerodata)
            chinfo['Data'] = numpy.hstack((chinfo['Data'], cordata[SRAMPAD:]))
        chinfo['Data'][0:4]=[zerodata]*4



    @setting(211, 'SRAM Analog Delay', channel=['(sw)'], delay=['v[ns]'], correct=['b'])
    def add_analog_delay(self, c, channel, delay, correct=True):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['Analogs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['Analogs'][channel]

        if correct:
            cxn = self.client
            p = cxn.dac_calibration.packet(context = c.ID)
            p.board  (chinfo['Info']['Board'][1])
            p.dac    (chinfo['Info']['DAC'][1])
            p.correct([0])
            zerodata = (yield p.send()).correct[0]
        else:
            zerodata = 0
            
        if len(chinfo['Data'])==0:
            chinfo['Data']=[zerodata]*(int(delay.value)+SRAMPAD)
        else:
            chinfo['Data']=numpy.hstack((chinfo['Data'], [zerodata]*int(delay.value)))


    @setting(220, 'SRAM Trigger Pulse', channel=['(sw)'], length=['v[ns]'],
                                        returns=['w'])
    def add_trigger_pulse(self, c, channel, length):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['Triggers']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['Triggers'][channel]

        n = int(length.value)
        if n>0:
            chinfo['Data'].append((True, n))
        return n


    @setting(221, 'SRAM Trigger Delay', channel=['(sw)'], length=['v[ns]'],
                                        returns=['w'])
    def add_trigger_delay(self, c, channel, length):
        if 'Experiment' not in c:
            raise NoExperimentError()
        if channel not in c['Experiment']['Triggers']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        #goto_sram(c)
        chinfo = c['Experiment']['Triggers'][channel]

        n = int(length.value)
        if n>0:
            chinfo['Data'].append((False, n))
        return n

        
    @setting(299, 'Memory Call SRAM', returns=['*s'])
    def finish_sram(self, c):
        if 'Experiment' not in c:
            raise NoExperimentError()
        # figure out longest SRAM block
        longest = 24
        for info in c['Experiment']['IQs'].values():
            if len(info['Data'][0])>longest:
                longest = len(info['Data'][0])
        for info in c['Experiment']['Analogs'].values():
            if len(info['Data'])>longest:
                longest = len(info['Data'])
        for info in c['Experiment']['Triggers'].values():
            totalcount = SRAMPREPAD
            for val, count in info['Data']:
                totalcount+=count
            if totalcount>longest:
                longest = totalcount
        # make sure SRAM length is divisible by 4
        longest = (longest + 3) & 0xFFFFFC

        # generate empty SRAM data (NOT USING CORRECT DAC ZEROS YET!)
        srams = dict([(board, numpy.array([0]*longest)) for board in c['Experiment']['FPGAs']])

        cxn = self.client
        
        # Fill in data
        for info in c['Experiment']['IQs'].values():
            if DEBUG==2:
                p = cxn.data_server.packet()
                p.open_session('debug')
                p.new_dataset('IQ data')
                p.add_independent_variable('Time')
                p.add_dependent_variable('real')
                p.add_dependent_variable('imag')
                p.add_datapoint([[t, d[0], d[1]][i] for t, d in enumerate(zip(*info['Data'])) for i in range(3)])
                yield p.send()
                
            srams[info['Info']['Board'][1]][0:len(info['Data'][0])] |= \
                (numpy.array(info['Data'][0]).astype(int) & 0x3FFF) + \
               ((numpy.array(info['Data'][1]).astype(int) & 0x3FFF) << 14)
            
        for info in c['Experiment']['Analogs'].values():
            if DEBUG==2:
                p = cxn.data_server.packet()
                p.open_session('debug')
                p.new_dataset('Analog data')
                p.add_independent_variable('Time')
                p.add_dependent_variable('amplitude')
                p.add_datapoint([[t, d][i] for t, d in enumerate(info['Data']) for i in range(2)])
                yield p.send()
                
            shift = info['Info']['DAC'][0]*14
            srams[info['Info']['Board'][1]][0:len(info['Data'])] |= \
                (numpy.array(info['Data']).astype(int) & 0x3FFF) << shift

        for info in c['Experiment']['Triggers'].values():
            mask = 1 << (info['Info']['Trigger'][0] + 28)
            ofs = SRAMPREPAD
            for val, count in info['Data']:
                if val:
                    srams[info['Info']['Board'][1]][ofs: ofs+count] |= mask
                ofs += count

        # add new data onto SRAM
        for board, data in srams.items():
            startaddr = len(c['Experiment']['SRAM'][board])/4
            c['Experiment']['SRAM'][board] += data.tostring()
            endaddr = len(c['Experiment']['SRAM'][board])/4 - 1

        # add call command into memories
        callsram = [0x800000 + (startaddr & 0x0FFFFF),
                    0xA00000 + (  endaddr & 0x0FFFFF),
                    0xC00000]
        for value in c['Experiment']['Memory'].values():
            value.extend(callsram)

        returnValue(srams.keys())

    

    @setting(1000, 'Run', stats=['w'],
                          setuppkts=['*((ww){context}, s{server}, *(s{setting}, ?{data}))'],
                          returns=['*2w'])
    def run_experiment(self, c, stats, setuppkts=None):
        if 'Experiment' not in c:
            raise NoExperimentError()

        fpgas = [fpga for fpga in c['Experiment']['FPGAs']]
        if len(c['Experiment']['TimerStopped'])<len(fpgas):
            raise QubitTimerNotStoppedError()

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
        p.start_delay([0]*len(fpgas))
        if setuppkts is None:
            p.run_sequence(stats)
        else:
            p.run_sequence(stats, True, setuppkts)
        timing = (yield p.send()).run_sequence
        result = []
        for qname in self.Setups[c['Experiment']['Setup']]['Qubits']:
            qubit = self.getQubit(qname)
            fpga = qubit['Timing'][1]
            result.append(timing[fpgas.index(fpga)])

        returnValue(result)

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
