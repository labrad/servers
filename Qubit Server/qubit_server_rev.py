# Copyright (C) 2009 Matthew Neeley
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

"""
## BEGIN NODE INFO
[info]
name = Qubits 2
version = 1.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
## END NODE INFO
"""

from labrad import types as T
from labrad.server import LabradServer, setting

from twisted.internet.defer import inlineCallbacks, returnValue

import numpy
from scipy.signal import slepian

SRAMPREPAD  = 20
SRAMPOSTPAD = 80

SRAMPAD = SRAMPREPAD + SRAMPOSTPAD

REGISTRY_PATH = ['', 'Servers', 'Qubit Server', '__new__']

"""
# configure hardware:
FPGA boards: - board groups, daisy chain order, delays, mode (analog or uwave or other)
- info about which board group is connected to which ethernet port (stored in ghz_dac registry entry)

DC Rack: - rack groups, board types for different numbers.
- Possibly want to store zero calibration data for different channels?
- info about which rack is connected to which serial port (stored in dc_rack registry entry)

uwave sources: - don't necessarily need anything special here



# configure wiring (stored in registry):
# go from GHz DAC board to FastBias/Preamp
'DR Lab FPGA 6', 'FO 0' => 'DR Lab FastBias 5', 'A'
(one of 'FO 0', 'FO 1')
'DR Lab FGPA 6', 'FI' => 'DR Lab Preamp 4', 'A'

# go from FastBias/Preamp to GHz DAC board
'DR Lab FastBias 5', 'A' => 'DR Lab FPGA 6', 'FO 1'
(one of 'A', 'B', 'C', 'D')

# optional: go from fridge bottom plate to fridge top plate, and from top plate to DC rack

# go between microwave sources and GHz DAC boards (if they are set for microwaves)
# error if this board is not set for microwaves or this anritsu is not connected to a DAC board
'DR GPIB Bus GPIB0::6' => 'DR Lab FPGA 5'
'DR Lab FPGA 5' => 'DR GPIB Bus GPIB0::6'


# configure qubits (stored in registry):
# now, define qubits and other devices
qubit0 = {'uwave': IQChannel('DR Lab FPGA 6'),
          'meas': AnalogChannel('DR Lab FPGA 5', 'DAC 0'),
          'flux': FastBiasChannel('DR Lab FastBias 3', 'A'),
          'squid': FastBiasChannel('DR Lab FastBias 2', 'A'),
          'timing': PreampChannel('DR Lab Preamp 1', 'A')
          }

other devices can have other names and any number of channels, etc.
constraints:
- squid and timing should go to the same DAC board, to have accurate timing (but don't check here)
- are there other things to check here, or do we defer it all to execution time?


# create sequence:
- automatically create setup packets for:
    - microwave sources
    - preamp boards

- add memory commands (including call SRAM blocks)
    - these happen in parallel across all memory channels
- add SRAM data (in named blocks)

# run sequence:
- this is where everything gets compiled and run (resolve wiring, etc.)
- could add a short delay to memory sequence of master immediately before SRAM to ensure synchronization
"""

def dacNameToNum(dac):
    dacs = {'DAC A': 0, 'DAC B': 1}
    if dac not in dacs:
        raise Exception('Invalid DAC name: %s' % dac)
    return dacs[dac]

def triggerNameToNum(trig):
    trigs = {'S 0': 0, 'S 1': 1, 'S 2': 2, 'S 3': 3}
    if trig not in trigs:
        raise Exception('Invalid Trigger name: %s' % trig)
    return trigs[trig]

NUM_FO_CHANNELS = 2
def foNameToNum(fo):
    fos = {'FO 0': 0, 'FO 1': 1}
    if fo not in fos:
        raise Exception('Invalid FO name: %s' % fo)
    return fos[fo]

class Setup(object):
    @classmethod
    def fromName(cls, name):
        if name not in cls._setups:
            raise SetupNotFoundError(name)
        return Setup()
        
    def __init__(self):
        pass

class Device(object):
    pass

class Qubit(Device):
    def getTimingBoard(self):
        return True

class DACboard(object):
    """Represents a single GHz DAC board."""
    def __init__(self, name):
        self.name = name
        self.startCount = 0
        self.stopCount = 0
        
    @property
    def started(self):
        return self.startCount == self.stopCount + 1
        
    def startTimer(self):
        if self.started:
            raise Exception("Timer %s already started." % self.name)
        self.startCount += 1
        
    def stopTimer(self):
        if not self.started:
            raise Exception("Timer %s was not started." % self.name)
        self.stopCount += 1

class Channel(object):
    pass

class IQChannel(Channel):
    def setAnritsuState(self, data):
        if data is None:
            pass
        else:
            freq, amp = data

class Experiment(object):
    def __init__(self, setupName):
        self.setup = Setup.fromName(setupName)
        self.setup.validate()
        self.channels = {}
        
    def getAllDevices(self):
        return sorted((d, d.type) for d in self.devices.values())
        
    def getDevices(self, devType):
        """return a list of devices of the specified type"""
        
    def getChannel(self, device, chan, chanType=None):
        # raise ChannelNotFoundError if not found
        # check channelType if given
        return self.devices[device][chan]

class QubitServer(LabradServer):
    """This server helps build sequences for controlling qubits
    and other devices with the GHz DAC and DC Rack setup.
    """
    name = 'Qubits'

    def getExperiment(self, c):
        """Get the current experiment in a context."""
        if 'experiment' not in c:
            raise NoExperimentError()
        return c['experiment']
        
    def getChannel(self, c, chan, chanType=None):
        expt = self.getExperiment(c)
        dev, chan = chan
        return expt.getChannel(dev, chan, chanType)

    @inlineCallbacks
    def initServer(self):
        self.devices = {}
        self.setups = {}


    @setting(100, 'Experiment New', setup_name='s', returns='*(s{deviceName} s{deviceType})')
    def expt_new(self, c, setup_name):
        """Begins a new experiment with the given setup.
        
        Returns a list of devices involved in this experimental
        setup and their types (e.g. qubit, resonator, etc.)
        """
        expt = c['experiment'] = Experiment(setup_name)
        return expt.getAllDevices()

    @setting(101, 'Experiment Involved Devices', device_type='s', returns='*s')
    def expt_get_devices(self, c, device_type=None):
        """Get a list of devices in the current experiment of the specified type.
        
        If no device type is specified, a list of all devices will be returned.
        """
        # TODO: this needs work
        expt = self.getExperiment(c)
        return expt.getDevices(device_type)

    @setting(200, 'Experiment Set Anritsu',
                  data=['(ss): Turn Anritsu off',
                        '((ss)v[GHz]v[dBm]): Set Anritsu to this frequency and amplitude'],
                  returns='b')
    def expt_set_anritsu(self, c, data):
        """Specifies the Anritsu settings to be used for this experiment for the given channel."""
        if len(data) == 3:
            channel, frq, amp = data
            data = (frq, amp)
        else:
            channel = data
            data = None
        expt = self.getExperiment(c)
        chan = expt.getChannel(channel, 'IQ')
        return chan.setAnritsuState(data)

    @setting(201, 'Experiment Turn Off Deconvolution',
                  channels=['(ss): Do not deconvolve this channel',
                            '*(ss): Do not deconvolve these channels'],
                  returns='')
    def expt_dont_deconvolve(self, c, channels):
        """Turns off deconvolution for a given (set of) channel(s)

        NOTES:
        This feature can be used to reduce the overall load on LabRAD
        by reducing packet traffic between the Qubit Server and the
        DAC Calibration Server, for example in a spectroscopy experiment.
        """
        expt = self.getExperiment(c)
        if isinstance(channels, tuple):
            channels = [channels]
        for channel in channels:
            chan = expt.getChannel(channel)
            chan.deconvolved = False


    @setting(300, 'Memory Bias Commands', commands='*((ss)w)',
                                          delay='v[us]',
                                          returns='v[us]')
    def mem_send_bias_commands(self, c, commands, delay=T.Value(10, 'us')):
        """Adds bias box commands to the specified channels and NOOPs to all other channels"""
        expt = self.getExperiment(c)

        FOs = expt['FOs']
        mems = dict((board, [0x000000] * NUM_FO_CHANNELS)
                    for board in expt['FPGAs'])

        # insert commands into memories at location given by FO index
        for ch, cmd in commands:
            if ch not in FOs:
                raise QubitChannelNotFoundError(ch[1], ch[0])
            cmd_base = 0x100000 * (foNameToNum(FOs[ch]['FO']) + 1)
            command = cmd_base + (cmd & 0x0FFFFF)
            mems[FOs[ch]['FPGA']][FOs[ch]['FO']] = command

        # strip out empties
        maxmem = 0
        for vals in mems.values():
            try:
                while True:
                    vals.remove(0x000000)
            except:
                pass
            if len(vals) > maxmem:
                maxmem = len(vals)
                
        # make all the same length by padding with NOOPs
        for vals in mems.values():
            vals += [0x000000]*(maxmem - len(vals))

        # figure out how much delay is needed
        delay = max(int(delay.value * 25 + 0.9999999999) - maxmem - 2, 0)
        realdelay = T.Value((delay + maxmem + 2) / 25.0, 'us')
        delseq = []
        while delay > 0x0FFFFF:
            delseq.append(0x3FFFFF)
            delay -= 0x0FFFFF
        delseq.append(0x300000 + delay)

        # add sequences into memories
        for key, value in expt['Memory'].items():
            value.extend(mems[key])
            value.extend(delseq)
        return realdelay

    @setting(301, 'Memory Delay', delay='v[us]', returns='v[us]')
    def mem_add_bias_delay(self, c, delay):
        """Adds a delay to all channels"""
        expt = self.getExperiment(c)

        # figure out how much delay is needed
        delay = max(int(delay.value * 25 + 0.9999999999) - 2, 0)
        realdelay = T.Value((delay + 2) / 25.0, 'us')
        delseq = []
        while delay > 0x0FFFFF:
            delseq.append(0x3FFFFF)
            delay -= 0x0FFFFF
        delseq.append(0x300000 + delay)

        # add sequences into memories
        for value in expt['Memory'].values():
            value.extend(delseq)
        return realdelay

    @setting(302, 'Memory Start Timer', devices='*s', returns='v[us]')
    def mem_start_timer(self, c, devices):
        """Adds a 'Start Timer' command to the specified Devices and NOP commands to all other Devices."""
        expt = self.getExperiment(c)
        for dev in expt.getDevices():
            if dev.name in devices:
                dev.startTimer()
            else:
                dev.addMemNoop()
        return T.Value(1/25.0, 'us')

    @setting(303, 'Memory Stop Timer', qubits='*s', returns='v[us]')
    def mem_stop_timer(self, c, qubits):
        """Adds a 'Stop Timer' command to the specified Qubits and NOP commands to all other Qubits"""
        expt = self.getExperiment(c)
        for dev in expt.getDevices():
            if dev.name in devices:
                dev.stopTimer()
            else:
                dev.addMemNoop()
        return T.Value(1/25.0, 'us')
    
    @setting(311, 'Memory Call SRAM Block', block='s', returns='*s')
    def mem_call_sram(self, c, block):
        """Add memory commands to call the specified SRAM block.
        """
        expt = self.getExperiment(c)

        # build deconvolved SRAM content
        srams = yield self.buildSRAM(expt)
        
        # add new data onto SRAM
        for board, data in srams.items():
            startaddr = len(expt['SRAM'][board])/4
            expt['SRAM'][board] += data.tostring()
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


    @setting(400, 'SRAM Begin Block', name='s')
    def sram_begin_block(self, c, name):
        """Begin a new SRAM block with the specified name."""
        pass
    
    @setting(401, 'SRAM End Block')
    def sram_end_block(self, c):
        """End the SRAM block with the specified name."""
        pass


    @setting(410, 'SRAM IQ Data', channel='ss', data = ['*(vv)', '*c'])
    def sram_add_iq_data(self, c, channel, data):
        """Adds IQ data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        data = data.asarray
        # convert to complex data if it was tuples
        if len(data.shape) == 2:
            data = data[:,0] + data[:,1] * 1j
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))

    @setting(411, 'SRAM IQ Delay', channel='ss', delay='v[ns]')
    def sram_add_iq_delay(self, c, channel, delay):
        """Adds a delay in the IQ data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'IQs')        
        data = numpy.array([0+0j]*int(delay))
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(412, 'SRAM IQ Envelope', channel='ss', data='*v', mixfreq='v[MHz]', phaseshift='v[rad]')
    def sram_add_iq_envelope(self, c, channel, data, mixfreq, phaseshift):
        """Turns the given envelope data into IQ data with the specified Phase and
        Sideband Mixing. The resulting data is added to the specified Channel
        """
        chinfo = self.getChannel(c, channel, 'IQs')        
        tofs = len(chinfo['Data']) - SRAMPREPAD
        t = numpy.arange(len(data)) + tofs
        df = mixfreq.value / 1000.0
        phi = phaseshift.value
        data = data.asarray*numpy.exp(-2.0j*numpy.pi*df*t + 1.0j*phi)
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))

    @setting(413, 'SRAM IQ Slepian', channel='ss', amplitude='v', length='v[ns]', mixfreq='v[MHz]', phaseshift='v[rad]')
    def sram_add_iq_slepian(self, c, channel, amplitude, length, mixfreq, phaseshift):
        """Generates IQ data for a Slepian Pulse with the specified Amplitude, Width, Phase and
        Sideband Mixing. The resulting data is added to the specified Channel
        """
        length = int(length)
        data = float(amplitude) * slepian(length, 10.0/length)
        chinfo = self.getChannel(c, channel, 'IQs')        
        tofs = len(chinfo['Data']) - SRAMPREPAD
        t = numpy.arange(len(data)) + tofs
        df = mixfreq.value / 1000.0
        phi = phaseshift.value
        data = data * numpy.exp(-2.0j*numpy.pi*df*t + 1.0j*phi)
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data))


    @setting(420, 'SRAM Analog Data', channel='ss', data='*v')
    def sram_add_analog_data(self, c, channel, data):
        """Adds analog data to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Analogs')        
        chinfo['Data'] = numpy.hstack((chinfo['Data'], data.asarray))

    @setting(421, 'SRAM Analog Delay', channel='ss', delay='v[ns]')
    def sram_add_analog_delay(self, c, channel, delay):
        """Adds a delay to the analog data of the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Analogs')        
        chinfo['Data'] = numpy.hstack((chinfo['Data'], numpy.zeros(int(delay))))


    @setting(430, 'SRAM Trigger Pulse', channel='ss', length='v[ns]', returns='w')
    def sram_add_trigger_pulse(self, c, channel, length):
        """Adds a Trigger Pulse of the given length to the specified Channel"""
        chinfo = self.getChannel(c, channel, 'Triggers')        
        n = int(length.value)
        if n > 0:
            chinfo['Data'].append((True, n))
        return n

    @setting(431, 'SRAM Trigger Delay', channel='ss', length='v[ns]', returns='w')
    def sram_add_trigger_delay(self, c, channel, length):
        """Adds a delay of the given length to the specified Trigger Channel"""
        chinfo = self.getChannel(c, channel, 'Triggers')        
        n = int(length.value)
        if n > 0:
            chinfo['Data'].append((False, n))
        return n


    @inlineCallbacks
    def buildSRAM(self, expt):
        """Build the SRAM arrays from the commands specified to this point."""
        # Figure out longest SRAM block
        longest = max(len(expt[chname][ch]['Data'] + SRAMPOSTPAD
                          for chname in ['IQs', 'Analogs', 'Triggers']
                          for ch in expt[chname]))
        # make sure SRAM length is divisible by 4
        longest = ((longest + 3) / 4) * 4
        srams = dict((board, numpy.zeros(longest).astype('int')) for board in expt['FPGAs'])

        # deconvolve the IQ and Analog channels
        deconvolved = {}
        for chname in ['IQs', 'Analogs']:
            chans = expt[chname]
            for ch in chans:
                chinfo = chans[ch]
                if ch in expt['NoDeconvolve']:
                    d = numpy.hstack((chinfo['Data'], numpy.zeros(SRAMPOSTPAD)))
                    if chname == 'IQs':
                        d =  ((d.real*0x1FFF).astype('int') & 0x3FFF) + \
                            (((d.imag*0x1FFF).astype('int') & 0x3FFF) << 14)
                    else:                            
                        d =  ((d*0x1FFF).astype('int') & 0x3FFF)
                    deconvolved[chname, ch] = d
                    continue
                board = chinfo['Info']['Board']
                p = self.client.dac_calibration.packet()
                p.board(board)
                if 'Anritsu' in chinfo['Info']:
                    anritsu = chinfo['Info']['Anritsu']
                    frq = expt['Anritsus'][anritsu]
                    if frq is None:
                        d = numpy.hstack((chinfo['Data'], numpy.zeros(SRAMPOSTPAD)))
                        d =  ((d.real*0x1FFF).astype('int') & 0x3FFF) + \
                            (((d.imag*0x1FFF).astype('int') & 0x3FFF) << 14)
                        deconvolved[(chname, ch)] = d
                        continue
                    frq = frq[0]
                    p.frequency(frq)
                else:
                    dac = chinfo['Info']['DAC']
                    p.dac(dac)
                p.correct(numpy.hstack((chinfo['Data'], numpy.zeros(SRAMPOSTPAD))))
                ans = yield p.send()
                d = ans.correct
                if isinstance(d, tuple):
                    d = ((d[1].asarray & 0x3FFF) << 14) + (d[0].asarray & 0x3FFF)
                else:
                    d = d.asarray & 0x3FFF
                deconvolved[chname, ch] = d

        # plug data into srams
        for ch, info in expt['IQs'].items():
            l = len(deconvolved['IQs', ch])
            if l:
                srams[info['Info']['Board']][0:l]       |=  deconvolved['IQs', ch]
                srams[info['Info']['Board']][l:longest] |= [deconvolved['IQs', ch][0]] * (longest-l)
            
        for ch, info in expt['Analogs'].items():
            shift = datNameToNum(info['Info']['DAC']) * 14
            l = len(deconvolved['Analogs', ch])
            if l:
                srams[info['Info']['Board']][0:l]       |=  deconvolved['Analogs', ch]    << shift
                srams[info['Info']['Board']][l:longest] |= [deconvolved['Analogs', ch][0] << shift] * (longest-l)

        for info in expt['Triggers'].values():
            mask = 1 << (trigNameToNum(info['Info']['Trigger']) + 28)
            ofs = SRAMPREPAD
            for val, count in info['Data']:
                if val:
                    srams[info['Info']['Board']][ofs:ofs+count] |= mask
                ofs += count

        returnValue(srams)  
    
    @setting(1000, 'Run', stats='w',
                          setupPkts='*((ww){context}, s{server}, ?{((s?)(s?)(s?)...)})',
                          setupState='*s',
                          returns='*2w')
    def run_experiment(self, c, stats, setupPkts=None, setupState=[]):
        """Runs the experiment and returns the raw switching data"""
        expt = self.getExperiment(c)
        cxn = self.client

        # check that timer has been started and stopped for each fpga
        fpgas = list(expt['FPGAs'])
        started = expr['TimerStarted']
        stopped = expr['TimerStopped']
        for fpga in fpgas:
            if fpga not in started:
                raise QubitTimerNotStartedError(q)
            if fpga not in stopped or (stopped[fpga] != started[fpga]):
                raise QubitTimerNotStoppedError(q)

        # add branch instruction to end of memory sequence
        # TODO: make this a separate call to finalize and validate a sequence
        for value in expt['Memory'].values():
            value.append(0xF00000)

        # add anritsu packets to setup packets
        if len(expt['Anritsus']):
            pkt = []
            for anritsu, settings in expt['Anritsus'].items():
                pkt.append(('Select Device', anritsu))
                if isinstance(settings, tuple):
                    pkt.append(('Output', True))
                    pkt.append(('Frequency', settings[0]))
                    pkt.append(('Amplitude', settings[1]))
                    setupState.append('%s: %s@%s' % (anritsu, settings[0], settings[1]))
                else:
                    pkt.append(('Output', False))
                    setupState.append('%s: off' % (anritsu,))
            if setupPkts is None:
                setupPkts = []
            setupPkts.append(((long(cxn._cxn.ID), 1L), 'Anritsu Server', tuple(pkt)))

        # upload memory and SRAM data
        p = cxn.ghz_dacs.packet(context=c.ID)
        for fpga in fpgas:
            p.select_device(fpga)
            if len(expt['SRAM'][fpga]):
                p.sram_address(0)
                p.sram(expt['SRAM'][fpga])
            p.memory(expt['Memory'][fpga])

        # specify daisy chain order and timing
        fpgas.remove(expt['Master'])
        fpgas = [expt['Master']] + fpgas
        p.daisy_chain(fpgas)
        p.start_delay([0]*len(fpgas)) # TODO: do we need delays here?
        p.timing_order([self.getDevice(qname)['Timing'] for qname in self.setups[expt['Setup']]['devices']])
        
        # run sequence
        if setupPkts is None:
            p.run_sequence(stats)
        else:
            p.run_sequence(stats, True, setupPkts, setupState)
        answer = yield p.send()
        timing_data = answer.run_sequence.asarray
        returnValue(timing_data)


    ## diagnostic information

    @setting(105, 'Memory Current', returns='*(s*w)')
    def get_mem(self, c):
        """Returns the current Memory data to be uploaded to the involved FPGAs"""
        expt = self.getExperiment(c)
        return expt['Memory'].items()

    @setting(106, 'Memory Current As Text', returns='*s*2s')
    def get_mem_text(self, c):
        """Returns the current Memory data to be uploaded to the involved FPGAs as a hex dump"""
        expt = self.getExperiment(c)
        fpgas = expt['Memory'].keys()
        vals = expt['Memory'].values()
        dat = [["0x%06X" % vals[a][b] for a in range(len(vals))]
               for b in range(len(vals[0]))]
        return fpgas, dat

    @setting(230, 'SRAM Plot', session='*s', name='s', correct='b', returns=[])
    def plot_sram(self, c, session, name, correct=True):
        expt = self.getExperiment(c)
        cxn = self.client
        dv  = cxn.data_vault
        p   = dv.packet()
        yaxes = []
        for ch, qb in sorted(expt['IQs'].keys()):
            yaxes.append(('Amplitude', "Real part of IQ channel '%s' on Qubit %d" % (ch, qb), "a.u."))
            yaxes.append(('Amplitude', "Imag part of IQ channel '%s' on Qubit %d" % (ch, qb), "a.u."))
        for ch, qb in sorted(expt['Analogs' ].keys()):
            yaxes.append(('Amplitude', "Analog channel '%s' on Qubit %d" % (ch, qb), "a.u."))
        for ch, qb in sorted(expt['Triggers'].keys()):
            yaxes.append(('Amplitude', "Trigger channel '%s' on Qubit %d" % (ch, qb), "a.u."))
        dir = [''] + session.aslist
        p.cd(dir)
        p.new(name, [('Time', 'ns')], yaxes)
        yield p.send()

        if correct:
            # Build deconvolved SRAM content
            srams = yield self.buildSRAM(expt)
            # Extract corrected data from SRAM
            data = None
            for ch, info in sorted(expt['IQs'].items()):
                i  = (srams[info['Info']['Board']]      ) & 0x00003FFF
                q  = (srams[info['Info']['Board']] >> 14) & 0x00003FFF
                i-= ((i & 8192) >> 13) * 16384
                q-= ((q & 8192) >> 13) * 16384
                i = i.astype('float')/8192.0
                q = q.astype('float')/8192.0
                if data is None:
                    data = numpy.vstack((numpy.arange(0.0, float(len(i)), 1.0), i, q))
                else:
                    data = numpy.vstack((data, i, q))
                
            for ch, info in sorted(expt['Analogs'].items()):
                shift = dacNameToNum(info['Info']['DAC']) * 14
                d  = (srams[info['Info']['Board']] >> shift) & 0x00003FFF
                d -= ((d & 8192) >> 13) * 16384
                d = d.astype('float')/8192.0
                if data is None:
                    data = numpy.vstack((range(len(i)), d))
                else:
                    data = numpy.vstack((data, d))

            for ch, info in sorted(expt['Triggers'].items()):
                shift = trigNameToNum(info['Info']['Trigger']) + 28
                d  = (srams[info['Info']['Board']] >> shift) & 0x00000001
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
                        while (curtrigs[ch] is not None) and (curtrigs[ch][0] <= 0):
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
                    yield dv.add(data)
                t += 1

     
############
# Exceptions

class DeviceNotFoundError(T.Error):
    code = 1
    def __init__(self, name):
        self.msg = "Device '%s' not found" % name

class ChannelNotFoundError(T.Error):
    code = 2
    def __init__(self, name):
        self.msg = "Channel '%s' not found" % name

class DeviceNotFoundError(T.Error):
    code = 3
    def __init__(self, name):
        self.msg = "Device '%s' is not defined yet" % name

class DeviceExistsError(T.Error):
    code = 4
    def __init__(self, name):
        self.msg = "Qubit '%s' is already defined" % name

class NoDeviceSelectedError(T.Error):
    """No qubit is selected in the current context"""
    code = 5

class SetupNotFoundError(T.Error):
    code = 6
    def __init__(self, name):
        self.msg = "Setup '%s' is not defined yet" % name

class ResourceConflictError(T.Error):
    code = 7
    def __init__(self, board, channel):
        self.msg = "Resource conflict: Channel '%s' on board '%s' is used multiple times" % (channel, board)

class QubitChannelNotFoundError(T.Error):
    code = 8
    def __init__(self, qubit, channel):
        self.msg = "In the current experiment, there is no qubit '%d' with a channel '%s'" % (qubit, channel)

class QubitIndexNotFoundError(T.Error):
    code = 9
    def __init__(self, qubit):
        self.msg = "In the current experiment, there is no qubit '%d'" % qubit

class QubitTimerStartedError(T.Error):
    code = 10
    def __init__(self, qubit):
        self.msg = "The timer has already been started on qubit '%d'" % qubit

class QubitTimerNotStartedError(T.Error):
    code = 11
    def __init__(self, qubit):
        self.msg = "The timer has not yet been started on qubit '%d'" % qubit

class QubitTimerStoppedError(T.Error):
    code = 12
    def __init__(self, qubit):
        self.msg = "The timer has already been stopped on qubit '%d'" % qubit

class QubitTimerNotStoppedError(T.Error):
    """The timer needs to be started and stopped on all qubits at least once"""
    code = 13

class SetupExistsError(T.Error):
    code = 14
    def __init__(self, name):
        self.msg = "Experimental setup '%s' is already defined" % name

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
        self.msg = "Channel '%s' on qubit '%d' does not require deconvolution" % (channel, qubit)
        
class ContextNotFoundError(T.Error):
    code = 19
    def __init__(self, context):
        self.msg = "Context (%d, %d) not found" % context
        
##########
        
__server__ = QubitServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
