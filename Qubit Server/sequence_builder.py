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

from labrad import types as T
from labrad.server import LabradServer, setting

from twisted.internet.defer import inlineCallbacks, returnValue

from copy import deepcopy

import numpy
from scipy.signal import slepian

SRAMPREPAD  = 20
SRAMPOSTPAD = 80

SRAMPAD = SRAMPREPAD + SRAMPOSTPAD

REGISTRY_PATH = ['', 'Servers', 'Qubit Server', '__new__']

def grabFromList(element, options, error):
    if isinstance(element, str):
        if element not in options:
            raise error(element)
        element = options.index(element)
    if (element < 0) or (element >= len(options)):
        raise error(element)
    return element, options[element]


class QubitServer(LabradServer):
    """Build and run memory and SRAM sequences for a set of qubits.
    
    This server loads configuration and setup information from the
    registry that can be created by the Qubit Config Server.
    """
    name = 'Sequence Builder'

    def getQubit(self, name):
        if name not in self.qubits:
            raise QubitNotFoundError(name)
        return self.qubits[name]

    def getExperiment(self, c):
        if 'Experiment' not in c:
            raise NoExperimentError()
        return c['Experiment']

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
        self.FOchannels = ['FO 0', 'FO 1']
        self.FOcommands = [0x100000, 0x200000]
        # autoload all qubits and setups
        yield self.loadQubits()
        yield self.loadSetups()

    @inlineCallbacks
    def loadQubits(self):
        """Loads Qubit definitions from the Registry"""
        self.qubits = {}
        qubits = yield self.listVariables('Qubits')
        for qubit in qubits:
            print 'loading qubit "%s"...' % qubit
            self.qubits[qubit] = yield self.loadVariable('Qubits', qubit)

    @inlineCallbacks
    def loadSetups(self):
        """Loads Experimental Setup definitions from the Registry"""
        self.setups = {}
        setups = yield self.listVariables('Setups')
        for setup in setups:
            print 'loading setup "%s"...' % setup
            self.setups[setup] = yield self.loadVariable('Setups', subit)


    @setting(10000, 'Duplicate Context', prototype='ww')
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



    @setting(100, 'Experiment New', setup='s', returns='(*s*(s, w, s))')
    def new_expt(self, c, setup):
        """Begins a new experiment with the given setup and returns the needed data channels."""
        if setup not in self.setups:
            raise SetupNotFoundError(setup)
        result = []
        setup = self.setups[setup]
        
        supportfpgas = setup['Devices'].keys()
        for q in setup['Qubits']:
            qubit = self.getQubit(q)
            supportfpgas.remove(qubit['Timing'][1])
            
        expt = c['Experiment'] = {
            'Setup':         setup,
            'IQs':           {},
            'Analogs':       {},
            'Triggers':      {},
            'FOs':           {},
            'FPGAs':         setup['Devices'].keys(),
            'Master':        setup['Master'],
            'Memory':        dict((board, [0x000000])
                                  for board in setup['Devices'].keys()),
            'SRAM':          dict((board, '')
                                  for board in setup['Devices'].keys()),
            'InSRAM':        False,
            'TimerStarted':  {},
            'TimerStopped':  {},
            'NonTimerFPGAs': supportfpgas,
            'Anritsus':      dict((anritsu, None)
                                  for anritsu in setup['Anritsus']),
            'NoDeconvolve':  []
            }

        for qindex, qname in enumerate(setup['Qubits']):
            qindex += 1
            q = self.getQubit(qname)
            for ch, info in q['IQs'].items():
                data = numpy.zeros(SRAMPREPAD, dtype=complex)
                expt['IQs'][ch, qindex] = {'Info': info, 'Data': data}
                msg = "IQ channel '%s' on Qubit %d connected to %s"
                result.append((ch, qindex, msg % (ch, qindex, info['Anritsu'][1])))
                
            for ch, info in q['Analogs'].items():
                data = numpy.zeros(SRAMPREPAD)
                expt['Analogs'][ch, qindex] = {'Info': info, 'Data': data}
                msg = "Analog channel '%s' on Qubit %d"
                result.append((ch, qindex, msg % (ch, qindex)))
                
            for ch, info in q['Triggers'].items():
                expt['Triggers'][ch, qindex] = {'Info': info, 'Data': []}
                msg = "Trigger channel '%s' on Qubit %d"
                result.append((ch, qindex, msg % (ch, qindex)))
                
            for ch, info in q['FOs'].items():
                fo, fpga = info['FO'][1], info['Board'][1]
                if fo not in self.FOchannels:
                    raise ChannelNotFoundError(fo)
                fo = self.FOchannels.index(fo)
                expt['FOs'][ch, qindex] = {'FPGA': fpga, 'FO': fo}
                msg = "FO channel '%s' on Qubit %d"
                result.append((ch, qindex, msg % (ch, qindex)))
                
        return (setup['Qubits'], result)



    @setting(101, 'Experiment Set Anritsu',
                  data=['(sw): Turn Anritsu off',
                        '((sw)v[GHz]v[dBm]): Set Anritsu to this frequency and amplitude'],
                  returns='b')
    def set_anritsu(self, c, data):
        """Specifies the Anritsu settings to be used for this experiment for the given channel."""
        if len(data) == 3:
            channel, frq, amp = data
            data = (frq, amp)
        else:
            channel = data
            data = None
        expt = self.getExperiment(c)
        if channel not in expt['IQs']:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        anritsu = expt['IQs'][channel]['Info']['Anritsu'][1]
        anritsuinfo = expt['Anritsus']
        if data is None:
            newInfo = False
        else:
            newInfo = data
        if anritsuinfo[anritsu] is None:
            anritsuinfo[anritsu] = newInfo
        else:
            if anritsuinfo[anritsu] != newInfo:
                raise AnritsuConflictError()
        return anritsuinfo!=False


    @setting(102, 'Experiment Turn Off Deconvolution',
                  channels=['(sw): Do not deconvolve this channel',
                            '*(sw): Do not deconvolve these channels'],
                  returns='*(sw)')
    def dont_deconvolve(self, c, channels):
        """Turns off deconvolution for a given (set of) channel(s)

        NOTES:
        This feature can be used to reduce the overall load on the LabRAD
        system by reducing packet traffic between the Qubit Server and the
        DAC Calibration Server, for example in a spectroscopy experiment.
        """
        expt = self.getExperiment(c)
        if isinstance(channels, tuple):
            channels = [channels]
        for channel in channels:
            if (channel not in expt['IQs']) and (channel not in expt['Analogs']):
                if (channel in expt['Triggers']) or (channel in expt['FOs']):
                    raise QubitChannelNotDeconvolvedError(channel[1], channel[0])
                else:    
                    raise QubitChannelNotFoundError(channel[1], channel[0])
            if channel not in expt['NoDeconvolve']:
                expt['NoDeconvolve'].append(channel)
        return expt['NoDeconvolve']

    @setting(103, 'Experiment Involved Qubits', returns='*s')
    def get_qubits(self, c):
        """Returns the list of qubits involved in the current experiment"""
        expt = self.getExperiment(c)
        setup = self.setups[expt['Setup']]
        return setup['Qubits']

    @setting(105, 'Memory Current', returns='*(s*w)')
    def get_mem(self, c):
        """Returns the current Memory data to be uploaded to the involved FPGAs"""
        expt = self.getExperiment(c)
        return sorted(expt['Memory'].items())

    @setting(106, 'Memory Current As Text', returns='(*s*2s)')
    def get_mem_text(self, c):
        """Returns the current Memory data to be uploaded to the involved FPGAs as a hex dump"""
        expt = self.getExperiment(c)
        mem = expt['Memory']
        fpgas = sorted(mem.keys())
        dat = [['0x%06X' % cmd for cmd in mem[fpga]] for fpga in fpgas]
        dat = zip(*dat)
        return (fpgas, dat)

    @setting(110, 'Memory Bias Commands', commands='*((sw)w)',
                                          delay='v[us]',
                                          returns='v[us]')
    def memory_bias_commands(self, c, commands, delay=T.Value(10, 'us')):
        """Adds bias box commands to the specified channels and delays to all other channels"""
        expt = self.getExperiment(c)

        FOs = expt['FOs']
        mems = dict((board, [0x000000]*len(self.FOchannels))
                    for board in expt['FPGAs'])

        # insert commands into memories at location given by FO index
        for ch, cmd in commands:
            if ch not in FOs:
                raise QubitChannelNotFoundError(ch[1], ch[0])
            fo, fpga = FOs[ch]['FO'], FOs[ch]['FPGA']
            command = self.FOcommands[fo] + (cmd & 0x0FFFFF)
            mems[fpga][fo] = command # TODO: this should be an append?

        # strip out empties
        for mem in mems.values():
            try:
                while True:
                    mem.remove(0x000000)
            except:
                pass
        maxmem = max(len(mem) for mem in mems.values())
        
        # make all the same length by padding with NOOPs
        for mem in mems.values():
            mem += [0x000000]*(maxmem - len(mem))
        
        for fpga, mem in expt['Memory'].items():
            mem.extend(mems[fpga])
            
        realdelay = self.addBiasDelay(expt, delay, maxmem)
        return realdelay


    @setting(111, 'Memory Delay', delay='v[us]', returns='v[us]')
    def memory_delay(self, c, delay):
        """Adds a delay to all channels"""
        expt = self.getExperiment(c)
        realdelay = self.addBiasDelay(expt, delay)
        return realdelay


    def addBiasDelay(self, expt, delay, memlen=0):
        """Adds a delay to all memory channels"""
        # figure out how much delay is needed
        delay = max(int(delay['us'] * 25 + 0.9999999999) - memlen - 2, 0)
        delseq = [0x3FFFFF] * (delay / 0x0FFFFF) + [0x300000 + (delay % 0x0FFFFF)]
        # add sequences into memories
        for mem in expt['Memory'].values():
            mem.extend(delseq)
        realdelay = T.Value((delay + 2) / 25.0, 'us')
        return realdelay



    @setting(112, 'Memory Start Timer', qubits='*w', returns='v[us]')
    def start_timer(self, c, qubits):
        """Adds a "Start Timer" command to the specified Qubits and NOP commands to all other Qubits"""
        expt = self.getExperiment(c)

        setup = self.setups[expt['Setup']]
        if not len(expt['TimerStarted']):
            fpgas = [fpga for fpga in expt['NonTimerFPGAs']]
        else:
            fpgas = []
        for q in qubits:
            if (q == 0) or (q > len(setup['Qubits'])):
                raise QubitIndexNotFoundError(q)
            qubit = self.getQubit(setup['Qubits'][q-1])
            fpga = qubit['Timing'][1]
            if fpga in expt['TimerStarted']:
                if fpga in expt['TimerStopped']:
                    if expt['TimerStopped'][fpga] < expt['TimerStarted'][fpga]:
                        raise QubitTimerStartedError(q)
                else:
                    raise QubitTimerStartedError(q)
            fpgas.append(fpga)
            
        for fpga in fpgas:
            if not fpga in expt['TimerStarted']:
                expt['TimerStarted'][fpga] = 1
            else:
                expt['TimerStarted'][fpga] += 1

        # add start command into memories
        for key, value in expt['Memory'].items():
            if key in fpgas:
                value.append(0x400000)
            else:
                value.append(0x000000)
        return T.Value(1/25.0, 'us')



    @setting(113, 'Memory Stop Timer', qubits='*w', returns='v[us]')
    def stop_timer(self, c, qubits):
        """Adds a "Stop Timer" command to the specified Qubits and NOP commands to all other Qubits"""
        expt = self.getExperiment(c)

        setup = self.setups[expt['Setup']]
        if not len(expt['TimerStopped']):
            fpgas = [fpga for fpga in expt['NonTimerFPGAs']]
        else:
            fpgas = []
        for q in qubits:
            if (q == 0) or (q > len(setup['Qubits'])):
                raise QubitIndexNotFoundError(q)
            qubit = self.getQubit(setup['Qubits'][q-1])
            fpga = qubit['Timing'][1]
            if fpga not in expt['TimerStarted']:
                raise QubitTimerNotStartedError(q)
            if fpga in expt['TimerStopped']:
                if expt['TimerStopped'][fpga] == expt['TimerStarted'][fpga]:
                    raise QubitTimerNotStartedError(q)
            fpgas.append(fpga)

        for fpga in fpgas:
            if not fpga in expt['TimerStopped']:
                expt['TimerStopped'][fpga] = 1
            else:
                expt['TimerStopped'][fpga] += 1
            
        # add stop command into memories
        for key, value in expt['Memory'].items():
            if key in fpgas:
                value.append(0x400001)
            else:
                value.append(0x000000)
        return T.Value(1/25.0, 'us')


    def getChannel(self, c, channel, chtype):
        expt = self.getExperiment(c)
        if channel not in expt[chtype]:
            raise QubitChannelNotFoundError(channel[1], channel[0])
        return expt[chtype][channel]


    @setting(199, 'SRAM Start Block', name='s')
    def start_sram_block(self, c, name):
        """Start building a new SRAM block that can be called by name."""
        pass

    @setting(200, 'SRAM IQ Data', channel='(sw)', data=['*(vv)', '*c'])
    def add_iq_data(self, c, channel, data):
        """Adds IQ data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        data = data.asarray
        # convert to complex data if it was tuples
        if len(data.shape) == 2:
            data = data[:,0] + data[:,1] * 1j
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(201, 'SRAM IQ Delay', channel='sw', delay='v[ns]')
    def add_iq_delay(self, c, channel, delay):
        """Adds a delay in the IQ data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        data = numpy.array([0+0j]*int(delay))
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(202, 'SRAM IQ Envelope', channel='sw', data='*v', mixfreq='v[MHz]', phaseshift='v[rad]')
    def add_iq_envelope(self, c, channel, data, mixfreq, phaseshift):
        """Turns the given envelope data into IQ data with the specified Phase and
        Sideband Mixing. The resulting data is added to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        tofs = len(chinfo['Data']) - SRAMPREPAD
        t = numpy.arange(len(data)) + tofs
        df = mixfreq.value / 1000.0
        phi = phaseshift.value
        data = data.asarray*numpy.exp(-2.0j*numpy.pi*df*t + 1.0j*phi)
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(203, 'SRAM IQ Slepian', channel='sw', amplitude='v', length='v[ns]', mixfreq='v[MHz]', phaseshift='v[rad]')
    def add_iq_slepian(self, c, channel, amplitude, length, mixfreq, phaseshift):
        """Generates IQ data for a Slepian Pulse with the specified Amplitude, Width, Phase and
        Sideband Mixing. The resulting data is added to the specified Channel"""

        length = int(length)
        data = float(amplitude)*slepian(length, 10.0/length)
        chinfo = self.getChannel(c, channel, 'IQs')        
        tofs = len(chinfo['Data']) - SRAMPREPAD
        t = numpy.arange(len(data)) + tofs
        df = mixfreq.value / 1000.0
        phi = phaseshift.value
        data = data*numpy.exp(-2.0j*numpy.pi*df*t + 1.0j*phi)
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(210, 'SRAM Analog Data', channel='sw', data='*v')
    def add_analog_data(self, c, channel, data):
        """Adds analog data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Analogs')        
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data.asarray))


    @setting(211, 'SRAM Analog Delay', channel='sw', delay='v[ns]')
    def add_analog_delay(self, c, channel, delay):
        """Adds a delay to the analog data of the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Analogs')        
        chinfo['Data'] = numpy.hstack((chinfo['Data'], numpy.zeros(int(delay))))


    @setting(220, 'SRAM Trigger Pulse', channel='sw', length='v[ns]', returns='w')
    def add_trigger_pulse(self, c, channel, length):
        """Adds a Trigger Pulse of the given length to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Triggers')        
        n = int(length.value)
        if n > 0:
            chinfo['Data'].append((True, n))
        return n


    @setting(221, 'SRAM Trigger Delay', channel='sw', length='v[ns]', returns='w')
    def add_trigger_delay(self, c, channel, length):
        """Adds a delay of the given length to the specified Trigger Channel"""
        chinfo = self.getChannel(c, channel, 'Triggers')        
        n = int(length.value)
        if n > 0:
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
                if l > longest:
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
                    if chname == 'IQs':
                        d =  ((d.real*0x1FFF).astype('int') & 0x3FFF) + \
                            (((d.imag*0x1FFF).astype('int') & 0x3FFF) << 14)
                    else:                            
                        d =  ((d*0x1FFF).astype('int') & 0x3FFF)
                    deconvolved[(chname, ch)] = d
                    continue
                board = expt[chname][ch]['Info']['Board'][1]
                p = cxn.dac_calibration.packet()
                p.board(board)
                if 'Anritsu' in expt[chname][ch]['Info']:
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
            l = len(deconvolved['IQs', ch])
            if l > 0:
                srams[info['Info']['Board'][1]][0:l]       |=  deconvolved[('IQs', ch)]
                srams[info['Info']['Board'][1]][l:longest] |= [deconvolved[('IQs', ch)][0]] * (longest-l)
            
        for ch, info in expt['Analogs'].items():
            shift = info['Info']['DAC'][0] * 14
            l = len(deconvolved[('Analogs', ch)])
            if l > 0:
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


    @setting(230, 'SRAM Plot', session='*s', name='s', correct='b', returns=[])
    def plot_sram(self, c, session, name, correct=True):
        expt = self.getExperiment(c)
        
        yaxes = []
        for ch, qb in sorted(expt['IQs'].keys()):
            yaxes.append(('Amplitude', 'Real part of IQ channel "%s" on Qubit %d' % (ch, qb), 'a.u.'))
            yaxes.append(('Amplitude', 'Imag part of IQ channel "%s" on Qubit %d' % (ch, qb), 'a.u.'))
        for ch, qb in sorted(expt['Analogs' ].keys()):
            yaxes.append(('Amplitude', 'Analog channel "%s" on Qubit %d' % (ch, qb), 'a.u.'))
        for ch, qb in sorted(expt['Triggers'].keys()):
            yaxes.append(('Amplitude', 'Trigger channel "%s" on Qubit %d' % (ch, qb), 'a.u.'))
        dir = [''] + session.aslist
        
        dv = self.client.data_vault
        ctx = dv.context()
        p = dv.packet(context=ctx)
        p.cd(dir)
        p.new(name, [('Time', 'ns')], yaxes)
        yield p.send()
        
        if correct:
            # Build deconvolved SRAM content
            srams = yield self.buildSRAM(expt)
            # Extract corrected data from SRAM
            data = None
            for ch, info in sorted(expt['IQs'].items()):
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
                
            for ch, info in sorted(expt['Analogs'].items()):
                shift = info['Info']['DAC'][0]*14
                d  = (srams[info['Info']['Board'][1]] >> shift) & 0x00003FFF
                d -= ((d & 8192) >> 13) * 16384
                d = d.astype('float')/8192.0
                if data is None:
                    data = numpy.vstack((range(len(i)), d))
                else:
                    data = numpy.vstack((data, d))

            for ch, info in sorted(expt['Triggers'].items()):
                shift = info['Info']['Trigger'][0] + 28
                d  = (srams[info['Info']['Board'][1]] >> shift) & 0x00000001
                d.astype('float')
                if data is None:
                    data = numpy.vstack((range(len(i)), d))
                else:
                    data = numpy.vstack((data, d))
            # Plot
            data = data.T
            yield dv.add(data, context=ctx)
        else:
            done = False
            t = 0
            curtrigs = {}
            while not done:
                done = True
                data = [float(t)]
                for ch in sorted(expt['IQs'].keys()):
                    if len(expt['IQs'][ch]['Data']) > t:
                        data.append(expt['IQs'][ch]['Data'][t].real)
                        data.append(expt['IQs'][ch]['Data'][t].imag)
                        done = False
                    else:
                        data.extend([0.0, 0.0])
                for ch in sorted(expt['Analogs'].keys()):
                    if len(expt['Analogs'][ch]['Data']) > t:
                        data.append(expt['Analogs'][ch]['Data'][t])
                        done = False
                    else:
                        data.append(0.0)
                if t < SRAMPREPAD:
                    for ch in sorted(expt['Triggers'].keys()):
                        data.append(0.0)
                    done = False
                else:
                    for ch in sorted(expt['Triggers'].keys()):
                        if ch not in curtrigs:
                            curtrigs[ch] = [-1, 0, False]
                        while (curtrigs[ch] is not None) and (curtrigs[ch][1] <= 0):
                            curtrigs[ch][0] += 1
                            if curtrigs[ch][0] >= len(expt['Triggers'][ch]['Data']):
                                curtrigs[ch] = None
                            else:
                                curtrigs[ch][2], curtrigs[ch][1] = expt['Triggers'][ch]['Data'][curtrigs[ch][0]]
                        if curtrigs[ch] is None:
                            data.append(0.0)
                        else:
                            curtrigs[ch][1] -= 1
                            if curtrigs[ch][2]:
                                data.append(1.0)
                            else:    
                                data.append(0.0)
                            done = False
                if not done:
                    yield dv.add(data, context=ctx)
                t += 1
      
      
    @setting(299, 'Memory Call SRAM', returns='*s')
    def finish_sram(self, c):
        """Constructs the final SRAM data from all the Channel data and adds the right
        "Call SRAM" command into the Memory of all Qubits to execute the SRAM data"""
        expt = self.getExperiment(c)

        # build deconvolved SRAM content
        srams = yield self.buildSRAM(c['Experiment'])
        
        # add new data onto SRAM
        for board, data in srams.items():
            startaddr = len(expt['SRAM'][board])/4
            c['Experiment']['SRAM'][board] += data.tostring()
            endaddr = len(expt['SRAM'][board])/4 - 1

        # clear current sram
        for info in expt['IQs'].values():
            info['Data'] = numpy.zeros(SRAMPREPAD, dtype=complex)
        for info in expt['Analogs'].values():
            info['Data'] = numpy.zeros(SRAMPREPAD)
        for info in expt['Triggers'].values():
            info['Data'] = []

        # add call command into memories
        callsram = [0x800000 + (startaddr & 0x0FFFFF),
                    0xA00000 + (  endaddr & 0x0FFFFF),
                    0xC00000]
        for mem in expt['Memory'].values():
            mem.extend(callsram)

        returnValue(srams.keys())
    
    @setting(1000, 'Run', stats='w',
                          setupPkts='*((ww){context}, s{server}, ?{((s?)(s?)(s?)...)})',
                          returns='*2w')
    def run_experiment(self, c, stats, setupPkts=None):
        """Runs the experiment and returns the raw switching data"""
        expt = self.getExperiment(c)
        setup = self.setups[expt['Setup']]
        cxn = self.client

        # check that all fpgas have been started and stopped appropriately
        fpgas = list(expt['FPGAs'])
        for fpga in fpgas:
            started, stopped = expt['TimerStarted'], expt['TimerStopped']
            if fpga not in started:
                raise QubitTimerNotStartedError(q)
            if fpga not in stopped or (stopped[fpga] < started[fpga]):
                raise QubitTimerNotStoppedError(q)
        
        # branch back to address = 0
        for mem in expt['Memory'].values():
            mem.append(0xF00000)
        
        # add setup packets for the anritsus
        # TODO: need to implement packet forwarding capability
        setupState = []
        if len(expt['Anritsus']):
            ctx = (long(cxn._cxn.ID), 1L)
            p = cxn['Anritsu Server'].packet(context=ctx)
            for anritsu, settings in expt['Anritsus'].items():
                p.select_device(anritsu)
                if isinstance(settings, tuple):
                    freq, amp = settings
                    p.output(True)
                    p.frequency(freq)
                    p.amplitude(amp)
                    setupState.append('%s: %s@%s' % (anritsu, freq, amp))
                else:
                    p.output(False)
                    setupState.append('%s: off' % anritsu)
            if setupPkts is None:
                setupPkts = []
            setupPkts.append(p)
        else:
            setupState = ['dont care']

        # create packet for the GHz DACs
        p = cxn.ghz_dacs.packet(context=c.ID)
        
        # upload memory and SRAM
        for index, fpga in enumerate(fpgas):
            p.select_device(fpga)
            if len(expt['SRAM'][fpga]) > 0:
                p.sram_address(0)
                p.sram(expt['SRAM'][fpga])
            p.memory(expt['Memory'][fpga])

        # setup daisy chain and timing order (master first)
        fpgas.remove(expt['Master'])
        fpgas = [expt['Master']] + fpgas
        p.daisy_chain(fpgas)
        p.timing_order([self.getQubit(qname)['Timing'][1] for qname in setup['Qubits']])
        p.start_delay([0]*len(fpgas)) # TODO: add start delay customization
        if setupPkts is None:
            p.run_sequence(stats)
        else:
            p.run_sequence(stats, True, setupPkts, setupState)
        answer = yield p.send()
        timing_data = answer.run_sequence.asarray
        returnValue(timing_data)


####################
# Registry Utilities

@inlineCallbacks
def loadTree(cxn, path=[], ctx=None):
    """Load a tree from the registry, rooted at the given path.
    
    If a context is specified, 
    """
    newCtx = cxn.context()
    
    def _load(path, listing):
        dirs, keys = listing
        p = cxn.registry.packet(context=newCtx)
        p.cd(path)
        for d in dirs:
            p.cd(d).dir(key=d).cd(1)
        for k in keys:
            p.get(k, key=k)
        ans = yield p.send()
        params = {}
        for d in dirs:
            params[d] = _load(path + [d], ans[d])
        for k in keys:
            params[k] = ans[k]
        for d in dirs:
            params[d] = yield params[d]
        returnValue(params)
    
    # get current path and directory listing
    p = cxn.registry.packet(context=newCtx)
    if ctx is not None:
        p.duplicate_context(ctx)
    p.cd(path).dir()
    ans = yield p.send()
    path, listing = ans.cd, ans.dir
    params = yield _load(path, listing)
    returnValue(params)
        
############
# Exceptions

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

class SetupNotFoundError(T.Error):
    code = 6
    def __init__(self, name):
        self.msg="Setup '%s' is not defined yet" % name

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
        
        
        
__server__ = QubitServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
