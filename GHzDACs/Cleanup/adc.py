"""
"""
import numpy as np

import fpga

# named functions
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock


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
            regs = self.regRun(self, RUN_MODE_AVERAGE_AUTO, 1, filterFunc,
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
        data = [(Is[i::nDemod], Qs[i::nDemod]) for i in xrange(nDemod)]
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
        raise RuntimeError("Check this function for correctness")
        a = np.fromstring(resp, dtype='<u1')
        raise RuntimeError("check parity of pll latch bits")
        return {
            'build': a[0],
            'noPllLatch': a[1]&1 == 1,
            'executionCounter': (a[3]<<8) + a[2]
        }


fpga.REGISTRY[('ADC', 2)] = ADC_Build2


class AdcRunner_Build4(AdcRunner_Build2):
    def __init__(self, dev, reps, runMode, startDelay, filter, channels,
                 triggerTable):
        self.dev = dev
        self.reps = reps
        self.runMode = runMode
        self.startDelay = startDelay
        self.filter = filter
        self.channels = channels
        self.triggerTable = triggerTable
        
        if self.runMode == 'average':
            self.mode = self.dev.RUN_MODE_AVERAGE_DAISY
            self.nPackets = self.dev.AVERAGE_PACKETS
        elif self.runMode == 'demodulate':
            self.mode = self.dev.RUN_MODE_DEMOD_DAISY
            raise RuntimeError("Following line is probably wrong")
            self.nPackets = reps
        else:
            raise Exception("Unknown run mode '%s' for board '%s'" \
                % (self.runMode, self.dev.devName))
        # 16us acquisition time + 10us packet transmit.
        # Not sure why the extra +1 is here
        raise RuntimeError("Following line is probably wrong")
        self.seqTime = fpga.TIMEOUT_FACTOR * (26E-6 * self.reps) + 1
    
    def loadPacket(self, page, isMaster):
        """Create pipelined load packet. For ADC this is the trigger table."""
        if isMaster:
            raise Exception("Cannot use ADC board '%s' as master." \
                % self.dev.devName)
        return self.dev.load(self.triggerTable)
    
    def runPacket(self, page, slave, delay, sync):
        """Create run packet.
        
        The unused arguments page, slave, and sync, in the call signature
        are there so that we could use the same call for DACs and ADCs.
        This is cheesey and ought to be fixed.
        """
        
        startDelay = self.startDelay + delay
        regs = self.dev.regRun(self.mode, self.reps, len(self.filter),
                               self.channels, self.monA, self.monB,
                               startDelay=startDelay, bitmask=self.bitmask)
        return regs


class ADC_Build4(ADC_Branch1):
    
    RUNNER_CLASS = AdcRunner_Build4
    
    # Build-specific constants
    DEMOD_CHANNELS = 4
    DEMOD_CHANNELS_PER_PACKET = 11
    DEMOD_TIME_STEP = 2 #ns
    AVERAGE_PACKETS = 32 #Number of packets per average mode execution
    AVERAGE_PACKET_LEN = 1024 #bytes
    TRIG_AMP = 255
    LOOKUP_TABLE_LEN = 256
    FILTER_LEN = 4096
    FILTER_DERPS = 4
    SRAM_WRITE_DERPS = 10
    SRAM_WRITE_PKT_LEN = 1024 # Length of the data portion, not address bytes
    LOOKUP_ACCUMULATOR_BITS = 16
    
    TRIGGER_TABLE_ENTRIES = 64
    TRIGGER_TABLE_DERP = 9
    
    # Methods to get bytes to be written to register
    
    def buildRunner(self, reps, info):
        """Get a runner for this board"""
        runMode = info['runMode']
        startDelay = info['startDelay']
        filter = info['filter']
        triggerTable = info['triggerTable']
        channels = dict((i, info[i]) for i in range(self.DEMOD_CHANNELS) \
                        if i in info)
        runner = self.RUNNER_CLASS(self, reps, runMode, startDelay, filter,
                                   channels, triggerTable)
        return runner
    
    @classmethod
    def regRun(cls, mode, reps, filterLen, demods, monA, monB, startDelay=0,
               bitmask=0):
        """Returns a numpy array of register bytes to run the board"""
        regs = np.zeros(self.REG_PACKET_LEN, dtype='<u1')
        regs[0] = mode
        regs[1:3] = littleEndian(startDelay, 2)
        regs[7:9] = littleEndian(reps, 2)
        
        if filterLen <= 1:
            raise Exception("Filter func length must be >= 2")
        regs[9:11] = littleEndian(filterLen - 1, 2)
        regs[11] = len(demods)
        regs[12] = bitmask
        regs[13], regs[14] = monA, monB
        for i in range(cls.DEMOD_CHANNELS):
            if i not in demods:
                continue
            addr = 15 + 4*i
            regs[addr:addr+2] = littleEndian(demods[i]['dPhi'], 2)
            regs[addr+2:addr+4] = littleEndian(demods[i]['phi0'], 2)
        return regs

    # Direct ethernet server packet creation methods
    
    def setup(self, filter, demods):
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        amps = ''
        for ch in xrange(self.DEMOD_CHANNELS):
            if ch in demods:
                cosineAmp = demods[ch]['cosineAmp']
                sineAmp = demods[ch]['sineAmp']
            else:
                cosineAmp = sineAmp = 0
            amps += '%s,%s;' % (cosineAmp, sineAmp)
        setupState = "%s: filter=%s, trigAmps=%s" % (self.devName, \
            filterFunc.tostring(), amps)
        return p, setupState
    
    def load(self, triggerData):
        """
        Create a direct ethernet packet to load sequence data.
        
        Sequence data is just the trigger table.
        """
        p = self.makePacket()
        self.makeTriggerTable(triggerData, p)
        return p
    
    # Direct ethernet server packet update methods
    
    @classmethod
    def makeTriggerTable(cls, data, p):
        """
        Add trigger table write to packet
        
        data - list of (count, delay) tuples
        p: packet to update
        """
        #Convert to little endian numpy array
        data = np.array(data, dtype='<i2').flatten()
        pkt = cls.pktWriteSram(cls.TRIGGER_TABLE_DERP, data)
        p.write(pkt.tostring())
    
    # board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _sendSRAM(self, filter, demods={}):
        """
        Write SRAM to the FPGA
        
        SRAM includes trig lookups, filter function, and trigger table
        """
        #Raise exception to see what's calling this method
        raise RuntimeError("_sendSRAM was called")
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        self.makeTriggerTable(data, p)
        yield p.send()
    
    # Externally available board communication methods
    # These run in test mode
    
    def runAverage(self, filterFunc, demods):
        @inlineCallbacks
        def func():
            regs = self.regRun(self.RUN_MODE_AVERAGE_AUTO, 1, len(filterFunc),
                               demods, monA, monB)
            p = self.makePacket()
            p.write(regs.tostring())
            p.timeout(T.Value(10, 's'))
            p.read(self.AVERAGE_PACKETS)
            ans = yield p.send()
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractAverage(packets))
    
    def runDemod(self, filterFunc, demods, triggerTable, monA, monB,
                 bitmask=0):
        @inlineCallbacks
        def func():
            regs = self.regRun(self.RUN_MODE_DEMOD_AUTO, 1, len(filterFunc),
                               demods, monA, monB, bitmask=bitmask)
            p = self.makePacket()
            self.makeFilter(filterFunc, p)
            self.makeTrigLookups(demods, p)
            self.makeTriggerTable(triggerTable, p)
            p.write(regs.tostring())
            p.timeout(T.Value(10, 's'))
            p.read(1)
            ans =  yield p.send()
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractDemod(packets, \
                self.DEMOD_CHANNELS_PER_PACKET))
        
        return self.testMode(func)
    
    # Utility
    
    @staticmethod
    def processReadback(resp):
        raise NotImplementedError
    
    @staticmethod
    def extractDemod(packets, nDemod):
        raise NotImplementedError


fpga.REGISTRY[('ADC', 4)] = ADC_Build4


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
