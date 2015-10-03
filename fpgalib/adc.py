# -*- coding: utf-8 -*-
import logging
import numpy as np

import fpgalib.fpga as fpga

# named functions
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T
import labrad.support

from fpgalib.util import littleEndian, TimedLock

import fpgalib.mondict as mondict


### Base classes ###

class ADC(fpga.FPGA):
    """
    Base class for ADC builds
    
    Some functions are implemented here. I chose to do this in a few functions
    that I don't expect to change. Of course you can just override them in
    subclasses as necessary.
    """
    
    MAC_PREFIX = '00:01:CA:AA:01:'
    REG_PACKET_LEN = 59
    READBACK_LEN = 46
    
    # Start modes
    RUN_MODE_REGISTER_READBACK = 1
    RUN_MODE_AVERAGE_AUTO = 2
    RUN_MODE_AVERAGE_DAISY = 3
    RUN_MODE_DEMOD_AUTO = 4
    RUN_MODE_DEMOD_DAISY = 5
    RUN_MODE_CALIBRATE = 7
    
    @classmethod
    def macFor(cls, boardNumber):
        """Get the MAC address of an ADC board as a string."""
        return cls.MAC_PREFIX + ('0'+hex(int(boardNumber))[2:])[-2:].upper()
    
    @classmethod
    def isMac(mac):
        """Return True if this mac is for an ADC, otherwise False"""
        return mac.startswith(cls.MAC_PREFIX)
    
    # Life cycle methods
    
    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """Establish a connection to the board."""
        print('connecting to ADC board: %s (build #%d)'\
            % (self.macFor(board), build))

        self.boardGroup = group
        self.server = de
        self.cxn = de._cxn
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = self.macFor(board)
        self.devName = name
        self.serverName = de._labrad_name
        self.timeout = T.Value(1, 's')

        # Set up our context with the ethernet server.
        # This context is expired when the device shuts down.
        p = self.makePacket()
        p.connect(port)
        # ADC boards send packets with different lengths:
        # - register readback: 46 bytes
        # - demodulator output: 48 bytes
        # - average readout: 1024 bytes
        # so we do not require a specific length for received packets.
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        #p.source_mac(self.boardGroup.sourceMac)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()
    
    @inlineCallbacks
    def shutdown(self):
        """Called when this device is to be shutdown."""
        yield self.cxn.manager.expire_context(self.server.ID,
                                              context=self.ctx)
    
    # Register byte methods
    
    @classmethod
    def regPing(cls):
        """Returns a numpy array of register bytes to ping ADC register"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1
        return regs
    
    @classmethod
    def regPllQuery(cls):
        """Returns a numpy array of register bytes to query PLL status"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 1
        return regs
    
    @classmethod
    def regSerial(cls, bits):
        """Returns a numpy array of register bytes to write to PLL"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 6
        regs[3:6] = littleEndian(bits, 3)
        return regs
    
    @classmethod
    def regAdcRecalibrate(cls):
        """Returns a numpy array of register bytes to recalibrate ADC chips"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = 7
        return regs
    
    # Methods to get byte arrays to be written to the board
    
    @classmethod
    def pktWriteSram(cls, derp, data):
        """
        Get a numpy array of bytes to write one derp of SRAM
        
        data - ndarray: numeric data to be written. This must be formatted such
               that .tostring will yield the proper byte string for the direct
               ethernet packet.
        """
        assert 0 <= derp < cls.SRAM_WRITE_DERPS, \
            'SRAM derp out of range: %d' % derp 
        # Ensure data is a numpy array.
        # This should not be needed, as it should have happened already
        data = np.asarray(data)
        pkt = np.zeros(cls.SRAM_WRITE_PKT_LEN + 2, dtype='<u1')
        pkt[0:2] = littleEndian(derp, 2)
        pkt[2:2+len(data)] = data
        return pkt
    
    # Utility
    
    @staticmethod
    def readback2BuildNumber(resp):
        """Get build number from register readback"""
        a = np.fromstring(resp, dtype='<u1')
        return a[0]


class AdcRunner(object):
    pass


class ADC_Branch1(ADC):
    """Superclass for first branch of ADC boards"""
    
    # Direct ethernet server packet update methods
    
    @classmethod
    def makeFilter(cls, data, p):
        """
        Update a packet for the ethernet server with SRAM commands to upload
        the filter function.
        """
        for derp in range(cls.FILTER_DERPS):
            start = cls.SRAM_WRITE_PKT_LEN * derp
            end = start + cls.SRAM_WRITE_PKT_LEN
            pkt = cls.pktWriteSram(derp, data[start:end])
            p.write(pkt.tostring())
    
    @classmethod
    def makeTrigLookups(cls, demods, p):
        """
        Update a packet for the ethernet server with SRAM commands to upload
        Trig lookup tables.
        """
        derp = 4 # First 4 derps used for filter function
        channel = 0
        while channel < cls.DEMOD_CHANNELS:
            data = []
            for ofs in [0, 1]:
                ch = channel + ofs
                for func in ['cosine', 'sine']:
                    if ch in demods:
                        d = demods[ch][func]
                    else:
                        d = np.zeros(cls.LOOKUP_TABLE_LEN, dtype='<u1')
                    data.append(d)
            data = np.hstack(data)
            pkt = cls.pktWriteSram(derp, data)
            p.write(pkt.tostring())
            channel += 2 # two channels per sram packet
            derp += 1 # each sram packet writes one derp
    
    # board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _runSerial(self, data):
        """Run a command or list of commands through the serial interface."""
        for d in data:
            regs = self.regSerial(d)
            yield self._sendRegisters(regs, readback=False)
    
    # Externally available board communication methods
    # These run in test mode.
    
    def recalibrate(self):
        @inlineCallbacks
        def func():
            regs = self.regAdcRecalibrate()
            yield self._sendRegisters(regs, readback=False)
        return self.testMode(func)
    
    def initPLL(self):
        @inlineCallbacks
        def func():
            yield self._runSerial([0x1FC093, 0x1FC092, 0x100004, 0x000C11])
        return self.testMode(func)
    
    def runCalibrate(self):
        raise Exception("Depricated. Use recalibrate instead")
        @inlineCallbacks
        def func():
            # build register packet
            filterFunc=np.zeros(self.FILTER_LEN, dtype='<u1')
            filterStretchLen=0
            filterStretchAt=0
            demods={}
            regs = self.regRun(RUN_MODE_CALIBRATE, 1, filterFunc,
                filterStretchLen, filterStretchAt, demods)
    
            # create packet for the ethernet server
            p = self.makePacket()
            p.write(regs.tostring()) # send registry packet
            yield p.send() #Send the packet to the direct ethernet server
            returnValue(None)
        return self.testMode(func)
    
    # Utility
    
    @staticmethod
    def extractAverage(packets):
        """Extract Average waveform from a list of packets (byte strings)."""
        
        data = ''.join(packets)
        Is, Qs = np.fromstring(data, dtype='<i2').reshape(-1, 2).astype(int).T
        return (Is, Qs)


### Specific DAC build classes ###

class AdcRunner_Build1(AdcRunner):
    def __init__(self, dev, reps, runMode, startDelay, filter, channels):
        self.dev = dev
        self.reps = reps
        self.runMode = runMode
        self.startDelay = startDelay
        self.filter = filter
        self.channels = channels
        
        if self.runMode == 'average':
            self.mode = self.dev.RUN_MODE_AVERAGE_DAISY
            self.nPackets = self.dev.AVERAGE_PACKETS
        elif self.runMode == 'demodulate':
            self.mode = self.dev.RUN_MODE_DEMOD_DAISY
            self.nPackets = reps
        else:
            raise Exception("Unknown run mode '%s' for board '%s'" \
                % (self.runMode, self.dev.devName))
        # 16us acquisition time + 10us packet transmit.
        # Not sure why the extra +1 is here
        self.seqTime = fpga.TIMEOUT_FACTOR * (26E-6 * self.reps) + 1
    
    def pageable(self):
        """ADC sequence alone will never disable paging"""
        return True
    
    def loadPacket(self, page, isMaster):
        """
        Create pipelined load packet
        
        For this build, do nothing.
        """
        if isMaster:
            raise Exception("Cannot use ADC board '%s' as master." \
                % self.dev.devName)
        return None
    
    def setupPacket(self):
        """ Create non-pipelined setup packet."""
        return self.dev.setup(self.filter, self.channels)
    
    def runPacket(self, page, slave, delay, sync):
        """Create run packet.
        
        The unused arguments page, slave, and sync, in the call signature
        are there so that we could use the same call for DACs and ADCs.
        This is cheesey and ought to be fixed.
        """
        
        filterFunc, filterStretchLen, filterStretchAt = self.filter
        startDelay = self.startDelay + delay
        regs = self.dev.regRun(self.mode, self.reps, filterFunc,
                               filterStretchLen, filterStretchAt,
                               self.channels, startDelay)
        return regs
    
    def collectPacket(self, seqTime, ctx):
        """
        Collect appropriate number of ethernet packets for this sequence, then
        trigger run context.
        """
        return self.dev.collect(self.nPackets, seqTime, ctx)
    
    def triggerPacket(self, ctx):
        """Send a trigger to the master context"""
        return self.dev.trigger(ctx)
    
    def readPacket(self, timingOrder):
        """
        Read (or discard) appropriate number of ethernet packets, depending on
        whether timing results are wanted.
        """
        keep = any(s.startswith(self.dev.devName) for s in timingOrder)
        return self.dev.read(self.nPackets) if keep else \
            self.dev.discard(self.nPackets)
    
    def extract(self, packets):
        """Extract data coming back from a readPacket."""
        if self.runMode == 'average':
            return self.dev.extractAverage(packets)
        elif self.runMode == 'demodulate':
            return self.dev.extractDemod(packets,
                self.dev.DEMOD_CHANNELS_PER_PACKET)


class ADC_Build1(ADC_Branch1):
    """ADC build 1"""
    
    RUNNER_CLASS = AdcRunner_Build1
    
    # Build-specific constants
    DEMOD_CHANNELS = 4
    DEMOD_CHANNELS_PER_PACKET = 11
    DEMOD_PACKET_LEN = 46
    DEMOD_TIME_STEP = 2 #ns
    AVERAGE_PACKETS = 32 #Number of packets per average mode execution
    AVERAGE_PACKET_LEN = 1024 #bytes
    TRIG_AMP = 255
    LOOKUP_TABLE_LEN = 256
    FILTER_LEN = 4096
    FILTER_DERPS = 4
    SRAM_WRITE_DERPS = 9
    SRAM_WRITE_PKT_LEN = 1024 # Length of the data portion, not address bytes
    LOOKUP_ACCUMULATOR_BITS = 16
    
    def buildRunner(self, reps, info):
        """Get a runner for this board"""
        runMode = info['runMode']
        startDelay = info['startDelay']
        filter = (info['filterFunc'], info['filterStretchLen'], info['filterStretchAt'])
        channels = dict((i, info[i]) for i in range(self.DEMOD_CHANNELS) \
                        if i in info)
        runner = self.RUNNER_CLASS(self, reps, runMode, startDelay, filter,
                                   channels)
        return runner
    
    # Methods to get bytes to be written to register
    
    @classmethod
    def regRun(cls, mode, reps, filterFunc, filterStretchAt,
                  filterStretchLen, demods, startDelay=0):
        """Returns a numpy array of register bytes to run the board"""
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = mode
        regs[1:3] = littleEndian(startDelay, 2) #Daisychain delay
        regs[7:9] = littleEndian(reps, 2)       #Number of repetitions
        
        if len(filterFunc)<=1:
            raise Exception('Filter function must be at least 2')
        #Filter function end address. -1 comes from 0 indexing.
        regs[9:11] = littleEndian(len(filterFunc)-1, 2)
        #Stretch address for filter
        regs[11:13] = littleEndian(filterStretchAt, 2)
        #Filter function stretch length
        regs[13:15] = littleEndian(filterStretchLen, 2)
        
        for i in range(cls.DEMOD_CHANNELS):
            if i not in demods:
                continue
            addr = 15 + 4*i
            #Lookup table step per sample
            regs[addr:addr+2] = littleEndian(demods[i]['dPhi'], 2)
            #Lookup table start address
            regs[addr+2:addr+4] = littleEndian(demods[i]['phi0'], 2)
        return regs
    
    # Direct ethernet server packet creation methods
    
    def setup(self, filter, demods):
        filterFunc, filterStretchLen, filterStretchAt = filter
        p = self.makePacket()
        self.makeFilter(filterFunc, p)
        self.makeTrigLookups(demods, p)
        amps = ''
        for ch in xrange(self.DEMOD_CHANNELS):
            if ch in demods:
                cosineAmp = demods[ch]['cosineAmp']
                sineAmp = demods[ch]['sineAmp'] 
            else:
                cosineAmp = sineAmp = 0
            amps += '%s,%s;' % (cosineAmp, sineAmp) 
        setupState = '%s: filter=%s, trigAmps=%s' % (self.devName, \
            filterFunc.tostring(), amps)
        return p, setupState
    
    # Direct ethernet server packet update methods
    
    # board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _sendSRAM(self, filter, demods={}):
        """Write filter and sine table SRAM to the FPGA."""
        #Raise exception to see what's calling this method
        raise RuntimeError("_sendSRAM was called")
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        yield p.send()
    
    # Externally available board communication methods
    # These run in test mode.
    
    def runAverage(self, filterFunc, filterStretchLen, filterStretchAt,
                   demods):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = self.regRun(self, self.RUN_MODE_AVERAGE_AUTO, 1, filterFunc,
                filterStretchLen, filterStretchAt, demods)
            
            p = self.makePacket()
            p.write(regs.tostring())
            p.timeout(T.Value(10, 's'))
            p.read(self.AVERAGE_PACKETS)
            ans = yield p.send()
                    
            # parse the packets out and return data
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractAverage(packets))
            
        return self.testMode(func)
    
    def runDemod(self, filterFunc, filterStretchLen, filterStretchAt, demods):
        @inlineCallbacks
        def func():
            # build register packet
            regs = self.regRun(self.RUN_MODE_DEMOD_AUTO, 1, filterFunc,
                filterStretchLen, filterStretchAt, demods)
    
            # create packet for the ethernet server
            p = self.makePacket()
            self.makeFilter(filterFunc, p) # upload filter function
            # upload trig lookup tables, cosine and sine for each demod
            # channel
            self.makeTrigLookups(demods, p)
            p.write(regs.tostring()) # send registry packet
            p.timeout(T.Value(10, 's')) # set a conservative timeout
            p.read(1) # read back one demodulation packet
            ans = yield p.send() #Send the packet to the direct ethernet
            # server parse the packets out and return data. packets is a list
            # of 48-byte strings
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractDemod(packets,
                self.DEMOD_CHANNELS_PER_PACKET))
            
        return self.testMode(func)
    
    # Utility
    
    @staticmethod
    def processReadback(resp):
        """Process byte string returned by ADC register readback
        
        Returns a dict with following keys
            build - int: the build number of the board firmware
            noPllLatch - bool: True is unlatch, False is latch (I think)
            executionCounter - int: Number of executions since last start
        """
        raise RuntimeError("Check this function for correctness")
        a = np.fromstring(resp, dtype='<u1')
        raise RuntimeError("check parity of pll latch bits")
        return {
            'build': a[0],
            'noPllLatch': a[1]&1 == 1,
        }
    
    @staticmethod
    def extractDemod(packets, nDemod):
        """Extract Demodulation data from a list of packets (byte strings)."""
        #stick all data strings in packets together, chopping out last 4 bytes
        #from each string
        data = ''.join(data[:44] for data in packets)
        #Convert string of bytes into numpy array of 16bit integers. <i2 means
        #little endian 2 byte
        vals = np.fromstring(data, dtype='<i2')
        #Is,Qs are numpy arrays with the following format
        #[I0,I1,...,I_numChannels,    I0,I1,...,I_numChannels]
        #           1st data run                2nd data run    
        Is, Qs = vals.reshape(-1, 2).astype(int).T
        #Parse the IQ data into the following format
        #[(Is ch0, Qs ch0), (Is ch1, Qs ch1),...,(Is chnDemod, Qs chnDemod)]
        data = (Is, Qs)
        #data = [(Is[i::nDemod], Qs[i::nDemod]) for i in xrange(nDemod)]
        #data_saved = data
        # compute overall max and min for I and Q
        def getRange(pkt):
            Irng, Qrng = [ord(i) for i in pkt[46:48]]
            twosComp = lambda i: int(i if i < 0x8 else i - 0x10)
            Imax = twosComp((Irng >> 4) & 0xF) # << 12
            Imin = twosComp((Irng >> 0) & 0xF) # << 12
            Qmax = twosComp((Qrng >> 4) & 0xF) # << 12
            Qmin = twosComp((Qrng >> 0) & 0xF) # << 12
            return Imax, Imin, Qmax, Qmin
        
        ranges = np.array([getRange(pkt) for pkt in packets]).T
        Imax = int(max(ranges[0]))
        Imin = int(min(ranges[1]))
        Qmax = int(max(ranges[2]))
        Qmin = int(min(ranges[3]))
        return (data, (Imax, Imin, Qmax, Qmin))


fpga.REGISTRY[('ADC', 1)] = ADC_Build1


class AdcRunner_Build2(AdcRunner_Build1):
    pass


class ADC_Build2(ADC_Build1):
    """
    ADC build 2
    
    This build adds ability to read back the parity of the PLL latch bits.
    This should allow us to 
    """
    
    RUNNER_CLASS = AdcRunner_Build2
    
    @staticmethod
    def processReadback(resp):
        """Process byte string returned by ADC register readback
        
        Returns a dict with following keys
            build - int: the build number of the board firmware
            noPllLatch - bool: True is unlatch, False is latch (I think)
            executionCounter - int: Number of executions since last start
        """
        #raise RuntimeError("Check this function for correctness")
        a = np.fromstring(resp, dtype='<u1')
        #raise RuntimeError("check parity of pll latch bits")
        return {
            'build': a[0],
            'noPllLatch': a[1]&1 == 1,
            'executionCounter': (a[3]<<8) + a[2]
        }


fpga.REGISTRY[('ADC', 2)] = ADC_Build2

class AdcRunner_Build3(AdcRunner_Build2):
    pass

class ADC_Build3(ADC_Build2):
    RUNNER_CLASS = AdcRunner_Build3
 
fpga.REGISTRY[('ADC', 3)] = ADC_Build3


class AdcRunner_Build6(AdcRunner_Build2):
    pass


class ADC_Build6(ADC_Build2):
    """
    This is the same as ADC_Build2 but has more demodulator channels.
    """
    RUNNER_CLASS = AdcRunner_Build6
    
    # Build-specific constants
    DEMOD_CHANNELS = 6

fpga.REGISTRY[('ADC', 6)] = ADC_Build6

class AdcRunner_Build7(AdcRunner_Build2):
    
    def __init__(self, dev, reps, runMode, startDelay, channels, info):
        self.dev = dev
        self.reps = reps
        self.runMode = runMode
        self.startDelay = startDelay
        self.channels = channels
        self.info = info
        
        if self.runMode == 'average':
            self.mode = self.dev.RUN_MODE_AVERAGE_DAISY
            self.nPackets = self.dev.AVERAGE_PACKETS
        elif self.runMode == 'demodulate':
            self.mode = self.dev.RUN_MODE_DEMOD_DAISY
            iqPairsPerExpt = sum([rcount*rchan for rcount, rdelay, rlen, rchan in info['triggerTable']])
            packetsPerExpt = int(np.ceil(iqPairsPerExpt/float(self.dev.DEMOD_CHANNELS_PER_PACKET)))
            self.nPackets = reps * packetsPerExpt
            # print "(ADC) number of packets: %d" % (self.nPackets,)
            # print "(ADC) rcount: %s, rdelay: %s, rlen: %s, rchan: %s, iqPairsPerExpt: %s, packetsPerExpt: %s, reps: %s" % (rcount, rdelay, rlen, rchan, iqPairsPerExpt, packetsPerExpt, reps)
        else:
            raise Exception("Unknown run mode '%s' for board '%s'" \
                % (self.runMode, self.dev.devName))
        # 16us acquisition time + 10us packet transmit.
        # Not sure why the extra +1 is here
        statTime = 4e-9*sum([count*(delay+rlen) for count, delay, rlen, chan in info['triggerTable']])
        self.seqTime = fpga.TIMEOUT_FACTOR * (statTime * self.reps) + 1
        # print "sequence time: %f, timeout: %f" % (statTime, self.seqTime)
    
    def loadPacket(self, page, isMaster):
        """Create pipelined load packet. For ADC this is the trigger table."""
        # print "making ADC load packet"
        if isMaster:
            raise Exception("Cannot use ADC board '%s' as master." \
                % self.dev.devName)
        p = self.dev.load(self.info)
        # print("adc load packet: %s" % (str(p._packet)))
        return p
        
    def setupPacket(self):
        p = self.dev.setup(self.info)
        # print("ADC setup packet: %s" % (str(p[0]._packet),))
        return p
    
    def runPacket(self, page, slave, delay, sync):
        """Create run packet.
        
        The unused arguments page, slave, and sync, in the call signature
        are there so that we could use the same call for DACs and ADCs.
        This is cheesey and ought to be fixed.
        """
        startDelay = self.startDelay + delay
        regs = self.dev.regRun(self.mode, self.info, self.reps, startDelay=startDelay)
        # print("ADC run packet: %s" % (regs,))
        return regs    
    
    def extract(self, packets):
        """Extract data coming back from a readPacket."""
        if self.runMode == 'average':
            return self.dev.extractAverage(packets)
        elif self.runMode == 'demodulate':
            return self.dev.extractDemod(packets,
                self.info['triggerTable'], self.info.get('mode', 'iq'))

class ADC_Branch2(ADC):
    """Superclass for second branch of ADC boards"""
    
    # Direct ethernet server packet update methods
    
    @classmethod
    def makeTriggerTable(cls, triggerTable, p):
        """
        Page 0 of SRAM has a table defining ADC trigger repetition counts and delays
        
        SRAM Write:
        The controller must write to SRAM in the AD board to define two tables, a retrigger table to define multiple AD triggers for an experiment start, and a multiplier table for demodulation of the incoming signal for each demodulation channel.
        
        (1) The retrigger table defines multiple AD triggers per master start.  The table starts at address 0, then increments up (to a maximum 127) after performing the functions of each table entry, until it reaches a table entry with rdelay[15..8]=0, at which time the retriggering stops.  Note that an empty table with rdelay[15..9]=0 at the address 0 will not ever trigger the AD.  In the table entry, rdelay[15..0]+ 3 is the number of 4 ns cycles between the AD start (or last end of ADon) and the AD trigger.  After this delay, the AD is turned on for rlength[7..0]+1 cycles, during which ADon demultiplexer (don) is high.  The value rcount[15..0]+1 is the number of AD triggers per table entry.  An AD done signal pulses 3 cycles after the last ADon goes low.  Note that there is approximately 7 clock cycle delay that needs to be measured and taken into account to get demodulation time correct.  Channels 0 to rchan[3..0]-1 is read out; maximum rchan[3..0] is 11 for 12 channels.  If rchan[3..0]=0, then save data in bit readout mode - see below.
        
        Note that you have multiple triggers, as for the DAC board.  But for each trigger, you can have multiple retriggering to account for multiple AD demodulations during each sequence.  

        (1) The retrigger table is stored in SRAM memory with adrstart[20..8] = 0.  The Ethernet packet is given by

        l(0)	length[15..8]		set to 4; ( length[15..0]= 1024+2=1026 )
        l(1)	length[7..0]		set to 2

        d(0)	adrstart[15..8]		SRAM page for start address: middle bits = 0,
        d(1)	adrstart[23..16]	upper bits; size of SRAM implies bits [23..19] = 0

        d(2)	sram(+0)[7..0]		rcount[7..0](0)		+1 = number AD cycles
        d(3)	sram(+1)[7..0]		rcount[15..8](0)
        d(4)	sram(+2)[7..0]		rdelay[7..0](0)		+3= clock delay before Multiplier on
        d(5)	sram(+3)[7..0]		rdelay[15..8](0)	    (units of 4 ns)
        d(6)	sram(+4)[7..0]		rlength(7..0](0)	+1 = clock length of Multiplier on
        d(7)	sram(+5)[7..0]		rchan[3..0](0)		Number channels saved, 0=bit mode	    
        d(8)	sram(+6)[7..0]		spare			
        d(9)	sram(+7)[7..0]		spare			

        d(10)	sram(+8)[7..0]		rcount[7..0](1)
        ...
        d(1022)sram(+1022)[7..0]	rcount[15..8](127)
        ...
        d(1025)sram(+1022)[7..0]	spare

        """
        # takes trigger table and turns it into a packet for ADC
        
        if len(triggerTable) > 128: # no memory for more than 128 entries
            raise Exception("Trigger table max len = 128")
        if triggerTable[0][1] < 1:
            raise Exception("Trigger table row0 rdelay is 0")
        
        rlens = [row[1]<50 for row in triggerTable]
        
        # if there is a spacing of <50 clock cycles between demods then the FIFO gets backed up
        if any(rlens):
            count0 = triggerTable[0][0]
            rlen0 = triggerTable[0][1]
            if rlen0<50 and count0==1 and not any(rlens[1:]): # if its only the start delay, no exception
                pass
            else:
                raise Exception("rlen < 50 clock cycles (200 ns) can cause FIFO backup for 12 chans")
        
        data = np.zeros(cls.SRAM_RETRIGGER_PKT_LEN, dtype='<u1')
        
        data[0] = 0 # SRAM page for start address: middle bits = 0,
        data[1] = 0 # upper bits; size of SRAM implies bits [23..19] = 0
        
        for idx,entry in enumerate(triggerTable):
            currCount, currDelay, currLength, currChans = entry
            
            # WARNING: currChans defined in a funny way
            # if you want a trigger to measure a subset of channels,
            # those channels must be the lowest channels.
            # i.e. you can only read out:
            # (0, 0-1, 0-2, ... 0-11)
            # you cannot cherry pick which channels to read out 
            # as far as JK and TW understand it.
            # For now, we will not make use of currChans(rchan),
            # rather default it all channels always read out.
            
            # See documentation above
            currCount -= 1 # compensate for FPGA offsets
            currDelay -= 4 # compensate for FPGA offsets
            currLength -=1 # compensate for FPGA offsets
            
            midx = idx * 8 + 2
            data[midx:midx+2] = littleEndian(currCount, 2)
            data[midx+2:midx+4] = littleEndian(currDelay, 2)
            data[midx+4] = currLength
            data[midx+5] = currChans
            data[midx+6:midx+8] = littleEndian(0, 2) # spare
        
        p.write(data.tostring())
        
    @classmethod
    def makeMixerTable(cls, demods, p):
    
        """
        Page 1-12 of SRAM has the mixer tables for demodulators 0-11 respectively.

        (2) For the multiplier lookup tables, adrstart is taken from the following table  
        adrstart[20..8]= channel n + 1.  This offsets by 1 from the above trigger page.

        The Ethernet packet for channel n is:

        l(1)	length[15..8]		set to 4; ( length[15..0]= 1024+2=1026 )
        l(2)	length[7..0]		set to 2

        d(1)	adrstart[15..8]		SRAM page for start address: middle bits = n+1 
        d(2)	adrstart[23..16]	upper bits; size of SRAM implies bits [23..19] = 0

        d(3)	sram(+0)[7..0]		multsin(0)		Multiplier time 0
        d(4)	sram(+1)[7..0]		multcos(0)
        d(5)	sram(+2)[7..0]		multsin(1)		Multiplier time 1 (1/2 clock, 2ns)
        d(6)	sram(+3)[7..0]		multcos(1)
        ...
        d(1025)sram(+1022)[7..0]	multsin(511)
        d(1026)sram(+1023)[7..0]	multcos(511)
        """

        for idx,demod in enumerate(demods):
            data = np.zeros(cls.SRAM_MIXER_PKT_LEN, dtype='<i1')
            # retrigger table is page 0, mixer tables are pages 1-13, factor of 4 from stripping least significant bits
            data[0:2] = littleEndian((idx+1),2) # SRAM page address
            mixerTable = demod['mixerTable']
            for tidx, row in enumerate(mixerTable):
                I, Q = row
                data[(tidx*2)+2] = I
                data[(tidx*2+1)+2] = Q
                
            p.write(data.tostring())
        
    # board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _runSerial(self, data):
        """Run a command or list of commands through the serial interface."""
        for d in data:
            regs = self.regSerial(d)
            yield self._sendRegisters(regs, readback=False)
    
    # Externally available board communication methods
    # These run in test mode.
    
    def recalibrate(self):
        @inlineCallbacks
        def func():
            regs = self.regAdcRecalibrate()
            yield self._sendRegisters(regs, readback=False)
        return self.testMode(func)
    
    def initPLL(self):
        @inlineCallbacks
        def func():
            yield self._runSerial([0x1FC093, 0x1FC092, 0x100004, 0x000C11])
        return self.testMode(func)
    
    # Utility
    
    @staticmethod
    def extractAverage(packets):
        """Extract Average waveform from a list of packets (byte strings)."""
        
        data = ''.join(packets)
        Is, Qs = np.fromstring(data, dtype='<i2').reshape(-1, 2).astype(int).T
        return (Is, Qs)

class ADC_Build7(ADC_Branch2):
    """ADC build 7"""
    
    RUNNER_CLASS = AdcRunner_Build7
    
    # Build-specific constants
    DEMOD_CHANNELS = 12
    DEMOD_CHANNELS_PER_PACKET = 11
    DEMOD_PACKET_LEN = 46
    DEMOD_TIME_STEP = 2 #ns
    REGISTER_READBACK_PKT_LEN = 46
    AVERAGE_PACKETS = 16 #Number of packets per average mode execution
    AVERAGE_PACKET_LEN = 1024 #bytes
    SRAM_RETRIGGER_PKT_LEN = 1026 # Length of the data portion, not address bytes
    SRAM_MIXER_PKT_LEN = 1026 # Length of the data portion, not address bytes
    
    def buildRunner(self, reps, info):
        """Get a runner for this board"""
        logging.info("building runner with setting keys: {}".format(info.keys()))
        runMode = info['runMode']
        startDelay = info['startDelay']
        channels = dict((i, info[i]) for i in range(self.DEMOD_CHANNELS) \
                        if i in info)
        runner = self.RUNNER_CLASS(self, reps, runMode, startDelay,
                                   channels, info)
        return runner
    
    @classmethod
    def regRun(cls, mode, info, reps, startDelay=0):
        """
        Returns a numpy array of register bytes to run the board
        Register Write:
        These registers control the AD functions.  This card is always set in slave mode for daisychain initiation of AD functions (see GHzDAC board).  

        l(0)	length[15..8]		set to 0  ; ( length[15..0] = 59 )
        l(1)	length[7..0]		set to 59

        d(0)	start[7..0]     Output & command function
                                0 = off
                                1 = register readback
                                2 = average mode, auto start (use n=1)
                                3 = average mode, daisychain start
                                4 = demodulator mode, auto start (use n=1)
                                5 = demodulator mode, daisychain start
                                6 = set PLL of 1GHz clock with ser[23..0], no readback
                                7 = recalibrate AD converters, no readback
        d(1)	startdelay[7..0]	Start delay after daisychain signal, compensates for dchain delays 
        d(2)	startdelay[15..8]	  Note longer delays than for GHzDAC
        d(3) 	ser1[7..0]		8 lowest PLL bits of serial interface 
        d(4)	ser2[7..0]		8  middle PLL bits
        d(5)	ser3[7..0]		8 highest PLL bits
        d(6)	spare

        d(7)	n[7..0]			n = Number of averages in average mode
        d(8)	n[15..8]		n = Number of total events in demodulator mode
        d(9)	bitflip[7..0]		XOR mask for bit readout	
        d(10)	mon0[7..0] 		SMA mon0 and mon1 programming, like DAC board
        d(11)	mon1[7..0] 	
        ...
        d(58)	spare	
        
        """
        regs = np.zeros(cls.REG_PACKET_LEN, dtype='<u1')
        regs[0] = mode
        regs[1:3] = littleEndian(startDelay, 2) #Daisychain delay
        regs[7:9] = littleEndian(reps, 2)       #Number of repetitions
        regs[9] = littleEndian(0, 1)[0] #XOR bit flip mask

        mon0 = info.get('mon0', 'start')
        mon1 = info.get('mon1', 'don')

        if isinstance(mon0,str):
            mon0 = mondict.MONDICT[mon0]
        if isinstance(mon1,str):
            mon1 = mondict.MONDICT[mon1]

        regs[10] = mon0
        regs[11] = mon1
        
        return regs
    
    # Direct ethernet server packet creation methods
    def setup(self, info):
        """
        A setup packet is something that cannot pipeline, e.g. changing microwave source freq.
        """
        triggerTable = info['triggerTable']
        demods = [info[idx] for idx in range(self.DEMOD_CHANNELS) if idx in info]
        
        # demods = [info[idx] for idx in range(self.DEMOD_CHANNELS) if idx in info]
        p = self.makePacket("setup")
        self.makeTriggerTable(triggerTable, p)
        self.makeMixerTable(demods, p)
        
        triggerTableState = " ".join(['triggerTableState%d=%s' % (idx, triggerTable[idx]) for idx in range(len(triggerTable)) ])
        mixTableState = " ".join(['mixTable%d=%s' % (idx, demod['mixerTable']) for idx,demod in enumerate(demods) ])
        setupState = " ".join([triggerTableState,mixTableState])
        return p, setupState
    
    # Direct ethernet server packet update methods
    def load(self, info):
        """
        A load packet is something that can pipeline in some way, e.g. paging on the DAC boards.
        
        Create a direct ethernet packet to load sequence data.
        
        Sequence data is the trigger table and mixer table.
        """
        p = self.makePacket("load")
        return p    
    # board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _sendSRAM(self, filter, demods={}):
        """Write filter and sine table SRAM to the FPGA."""
        #Raise exception to see what's calling this method
        raise RuntimeError("_sendSRAM was called")
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        yield p.send()
    
    # Externally available board communication methods
    # These run in test mode.
    
    def registerReadback(self):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = self.regRun(self.RUN_MODE_REGISTER_READBACK, 0) # 0 reps?
            
            p = self.makePacket("registerReadback")
            p.write(regs.tostring())
            p.timeout(T.Value(10, 's'))
            p.read(1)
            ans = yield p.send()
                    
            # parse the packets out and return data
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.processReadback(packets[0]))
            
        return self.testMode(func)
    
    def runAverage(self):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = self.regRun(self.RUN_MODE_AVERAGE_AUTO, {}, 1)
            p = self.makePacket("runAverage")
            p.write(regs.tostring())
            p.timeout(T.Value(10, 's'))
            p.read(self.AVERAGE_PACKETS)
            ans = yield p.send()
                    
            # parse the packets out and return data
            packets = [data for src, dst, eth, data in ans.read]
            # print "average mode packets:"
            # for p in packets:
                # print "len: %d, first 64 byes:" % (len(p),)
                # print labrad.support.hexdump(p[0:64])
            returnValue(self.extractAverage(packets))
            
        return self.testMode(func)
    
    def runDemod(self, info):
        triggerTable = info['triggerTable']
        # Default to full length filter with half full scale amplitude
        demods = [info[idx] for idx in range(self.DEMOD_CHANNELS) if idx in info]
        #demods = dict((i, info[i]) for i in \
        #    range(self.DEMOD_CHANNELS) if i in info)
        mode = info['mode']    
        @inlineCallbacks
        def func():
            # build register packet
            regs = self.regRun(self.RUN_MODE_DEMOD_AUTO, info, 1)
    
            # create packet for the ethernet server
            p = self.makePacket("runDemod packet")
            self.makeTriggerTable(triggerTable,p)
            self.makeMixerTable(demods,p)
            p.write(regs.tostring()) # send registry packet
            p.timeout(T.Value(10, 's')) # set a conservative timeout
            totalReadouts = np.sum([ row[0]*row[3] for row in triggerTable])
            nPackets = int(np.ceil(totalReadouts/11.0))
            # print "Trying to read back %d packets with %d readouts" % (nPackets, totalReadouts)
            p.read(nPackets)
            logging.debug("about to send ADC packet in runDemod")
            ans = yield p.send() #Send the packet to the direct ethernet
            # server parse the packets out and return data. packets is a list
            # of 48-byte strings
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractDemod(packets, triggerTable, mode))
            
        return self.testMode(func)
    
    # Utility
    
    @staticmethod
    def processReadback(resp):
        """Process byte string returned by ADC register readback
        
        Returns a dict with following keys
            build - int: the build number of the board firmware
            noPllLatch - bool: True is unlatch, False is latch (I think)
            executionCounter - int: Number of executions since last start
            
        Register Readback:
        Registers are readback according to the above data fields and additional bytes given here.  Length of readback = 46.

        d(1)	build[7..0]		Build number of FPGA code.  
        d(2) 	clockmon[7..0]	bit0 = NOT(LED1 light) = no PLL in external 1GHz clock 
                                                bit1=dclkA output (phase of data stream)
                                bit2=dclkA delayed 1ns output
                                bit3=dclkB output
                                bit4=dclkB delayed 1ns output
        d(3)	trigs[7..0]		Count of number of triggers (same as DAC sramcount) 
        d(4) 	trigs[15..8]	 	  reset with start=2,3,4,5
        d(5) 	npackets[7..0]		Counter of number of packets received (reg and SRAM)
        d(6)	badpackets[7..0]	Number of packets received with bad CRC 
        d(7)	spare
        ...
        d(46)	spare[7..0]		set to 0	
        """
        a = np.fromstring(resp, dtype='<u1')
        return {
            'build': a[0],
            'noPllLatch': a[1]&1 == 1,
            'executionCounter': int(a[2]) + int(a[3] << 8),
            'nPackets': a[4],
            'badPackets': a[5]
            } 
    
    @classmethod
    def extractDemod(cls, packets, triggerTable, mode):
        """
        Extract Demodulation data from a list of packets (byte strings).
        
        Returns a tuple of (demodData, packet counters, readback counters)
        
        demodData is a 3-index numpy array with the following indices:
            0: channel
            1: stat
            2: trigger event
            3: I or Q
        
        Index 0 runs from 0 to rchans-1
        Index 1 runs from 0 to stats-1
        Index 2 runs from 0 to number of trigger events - 1
        Index 3 runs from 0(I) to 1(Q)
        
        After demodulation is done on each retrigger, demodulator output is put
        into a FIFO from channel 0 to numchan[7..0]-1.  Once 11 channels are
        in FIFO (44 bytes), or end of all retriggering, the ethernet packet is
        sent by pulling bytes out of FIFO, 44 bytes per output event.  Use
        numchan[7..0]=11 to read back every AD retrigger, since the writing of
        44 bytes will immediately trigger a FIFO read.  

        The FIFO stores 8192 bytes of data, or 186 packets.  This should be
        fine except for really long sequences.  If you have many retriggers
        that are closely spaced, with large number channels, the FIFO will
        overflow before having a chance to release the data.  The total
        Ethernet transmission time for one packet is around 5 us.  We have
        halved the averager size to 8 us to have larger FIFO memory.    

        When returning these packets, there is a running count from the end
        bytes countpack[7..0] and countrb[15..0] that increases for each
        packet. This data enables one to check if any packets were missed or to
        check for their ordering.    

        l(0)	length[15..8]		set to 0
        l(1)	length[7..0]		set to 48

        d(0)	Idemod0[7..0]		First channel ; Low byte of demodulator sum
        d(1)	Idemod0[15..8]		        High byte
        d(2)	Qdemod0[7..0]	First channel ; Quadrature output
        d(3)	Qdemod0[15..8]
        ...
        d(4)	Idemod1[7..0]		Second channel
        d(5)	Idemod1[15..8]	
        d(6)	Qdemod1[7..0]	
        d(7)	Qdemod1[15..8]
        ...
        d(40)	Idemod10[7..0]	11th channel
        d(41)	Idemod10[15..8]	
        d(42)	Qdemod10[7..0]	
        d(43)	Qdemod10[15..8]

        d(44)	countrb[7..0]		Running count of readback number since last start
        d(45)	countrb[15..8]		1st readback has countrb=1
        d(46)	countpack[7..0]	Packet counter, reset on start
        d(47)	spare [7..0]		
        
        """
        #stick all data strings in packets together, chopping out last 4 bytes
        #from each string
        rchans = [trig[3] for trig in triggerTable]
        nTrigger = [trig[0] for trig in triggerTable]
             
        # Allow only cases where rchans was the same for each entry in the
        # trigger table.
        # XXX This _really_ should have been checked earlier. Checking this
        # here is just stupid.
        if not rchans == len(rchans)*[rchans[0]]:
            msg = "Unequal rchans: {0} not supported".format(rchans)
            raise RuntimeError(msg)
        else:
            rchan = rchans[0]
        
        totalTriggers = np.sum(nTrigger)
        # pkt_per_stat = int(np.ceil((totalTriggers * rchan * 2.0)/cls.DEMOD_CHANNELS_PER_PACKET))
        pkt_per_stat = int(np.ceil((totalTriggers * rchan)/float(cls.DEMOD_CHANNELS_PER_PACKET)))
        # print 'totalTriggers: %s, rchan: %s, DEMOD_CHANNELS_PER_PACKET: %s' % (totalTriggers, rchan, cls.DEMOD_CHANNELS_PER_PACKET)
        reps = len(packets)//pkt_per_stat
        if len(packets) % pkt_per_stat:
            raise RuntimeError("wrong number of packets: %d not a multiple of pkt_per_stat: %d" % (len(packets), pkt_per_stat))

        
        # Puke all over the console output.
        #print "extract demod packets.  Total triggers: %d, rchan: %d" % (totalTriggers, rchan)
        #for p in packets:
        #    print "len: %d" % (len(p),)
        #    print labrad.support.hexdump(p)
        # print "total packets: %s, packets_per_stat: %s, reps: %s" % (len(packets), pkt_per_stat, reps)
        
        stat_pkt_list = [packets[idx*pkt_per_stat:pkt_per_stat*(idx+1)] for idx in range(reps)]
        # print "len of stat_pkt_list: %d, len stat_packet 0: %d" % (len(stat_pkt_list),len(stat_pkt_list[0]))
        all_data = []
        for stat_packet in stat_pkt_list:
            data = np.fromstring(''.join(data[:44] for data in stat_packet), dtype='<u1')
            pktCounters = [ord(pkt[46]) for pkt in stat_packet]
            readbackCounters = [ ord(pkt[44]) + ord(pkt[45])<<8 for pkt in stat_packet ]
            #print "packet counters: %s, readback counters: %s" % (pktCounters, readbackCounters)
            if mode=='iq':
                # Convert to 16-bit int array and chop garbage from last packet
                vals = np.fromstring(data, dtype='<i2')[:2*rchan*totalTriggers] 
                # Slowest varying index: time step, next slowest index : demodulator, fastest index: I vs Q
                #  Transpose first two indices to make demodulator first index 
                # Iq0[t=0], Qq0[t=0], Iq1[t=0], Qq1[t=0], Iq0[t=1], Qq0[t=1], Iq1[t=1], Qq1[t=1]
                #    
                #     goes to:
                # data[qubit][time_step][(I=0 | Q=1)]       
                #print "flat values: ", vals
                reshapedData = vals.reshape(totalTriggers , rchan, 2).astype(int)
                #print "reshaped data: ", reshapedData
                transposedData = reshapedData.transpose((1, 0, 2))
                #print "transposed data: ", transposedData
                all_data.append(transposedData)
            else:
                '''
                In bit readout mode, use rchan[7..0]=0.  Readout is only the sign bit of channels 0 to 7; one byte readout is designed for compactness to minimize number of Ethernet packets.  The bit is 0 if real quadrature of the channel is positive.  Bit is flipped with XOR mask bitflip[7..0] defined in register write.  Order of bits in output byte is [ch7..ch0].

                l(0)	length[15..8]		set to 0
                l(1)	length[7..0]		set to 48

                d(0)	bits1[7..0]		1st bitstring
                d(1)	bits2[7..0]		2nd bitstring
                ...	
                d(43)	bits44[7..0]		44th bitstring

                d(44)	countrb[7..0]		Running count of triggers since last start
                d(45)	countrb[15..8]		   1st readback has countrb=1
                d(46)	countpack[7..0]	Packet counter for retriggering, reset when countrb incr
                d(47)	spare [7..0]		   
                '''
                raise RuntimeError('Operation mode %s not implemented / available' % (mode,))
        #print "all data length: %d, element 0 size: %s" % (len(all_data), all_data[0].shape)
        # This makes stat the first index, giving us: data[stat][qubit][time_step][(I=0 | Q=1)]
        all_data = np.array(all_data)
        # data[stat][qubit][time_step][(I=0 | Q=1)] --> data[qubit][stat][time_step][(I=0 | Q=1)]
        all_data = all_data.transpose([1, 0, 2, 3])
        #print "all_data shape: ", all_data.shape
        return (all_data, pktCounters, readbackCounters)  # Only returning the packet counters of the last stat.  FIXME if you care about these

fpga.REGISTRY[('ADC', 7)] = ADC_Build7
