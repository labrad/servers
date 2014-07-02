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

class AdcRunner_Build7(AdcRunner_Build4):
    def __init__(self, dev, reps, runMode, startDelay, channels, 
                 triggerTable, mixerTable):
        self.dev = dev
        self.reps = reps
        self.runMode = runMode
        self.startDelay = startDelay
        self.channels = channels
        self.triggerTable = triggerTable
        self.mixerTable = mixerTable
        
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
        regs = self.dev.regRun(self.mode, self.reps, startDelay=startDelay)
        return regs    

class ADC_Branch2(ADC):
    """Superclass for second branch of ADC boards"""
    
    # Direct ethernet server packet update methods
    
    @classmethod
    def makeTriggerTable(cls, *args):
        """
        Page 0 of SRAM has a table defining ADC trigger repetition counts and delays
        """
        pass
    @classmethod
    def makeMixerTable(cls, *args):
        """
        Page 1-12 of SRAM has the mixer tables for demodulators 0-11 respectively.
        """
        pass
        
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
    AVERAGE_PACKETS = 16 #Number of packets per average mode execution
    AVERAGE_PACKET_LEN = 1024 #bytes
    SRAM_RETRIGGER_SRAM_PKT_LEN = 1024 # Length of the data portion, not address bytes
    SRAM_MIXER_SRAM_PKT_LEN = 1024 # Length of the data portion, not address bytes
    
    def buildRunner(self, reps, info):
        """Get a runner for this board"""
        runMode = info['runMode']
        startDelay = info['startDelay']
        triggerTable = info['triggerTable']
        mixerTable = info['mixerTable']
        channels = dict((i, info[i]) for i in range(self.DEMOD_CHANNELS) \
                        if i in info)
        runner = self.RUNNER_CLASS(self, reps, runMode, startDelay,
                                   channels, triggerTable, mixerTable)
        return runner
    
    @classmethod
    def regRun(cls, mode, reps, startDelay=0):
        """Returns a numpy array of register bytes to run the board
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
        regs[10:12] = littleEndian(0, 2) #SMA monitor channels
        
        return regs
    
    # Direct ethernet server packet creation methods
    
    def setup(self, info, demods):
        mixTables, triggerTable = info
        p = self.makePacket()
        self.makeTriggerTable(triggerTable, p)
        self.makeMixTable(mixTables, p)
        
        triggerTableState = " ".join(['triggerTableState%d=%s' % (idx, triggerTable[idx]) for idx in len(triggerTable) ])
        mixTableState = " ".join(['mixTable%d=%s' % (idx, mixTables[idx]) for idx in len(mixTables) ])

        return p, setupState, mixTableState
    
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
    
    def runAverage(self):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = self.regRun(self.RUN_MODE_AVERAGE_AUTO, 1)
            
            p = self.makePacket()
            p.write(regs.tostring())
            p.timeout(T.Value(10, 's'))
            p.read(self.AVERAGE_PACKETS)
            ans = yield p.send()
                    
            # parse the packets out and return data
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractAverage(packets))
            
        return self.testMode(func)
    
    def runDemod(self, triggerTable, mixerTable, demods, mode):
        @inlineCallbacks
        def func():
            # build register packet
            regs = self.regRun(self.RUN_MODE_DEMOD_AUTO, 1, filterFunc)
    
            # create packet for the ethernet server
            p = self.makePacket()
            self.makeTriggerTable(triggerTable,p)
            self.makeMixerTable(mixerTable,p)
            p.write(regs.tostring()) # send registry packet
            p.timeout(T.Value(10, 's')) # set a conservative timeout
            p.read(1) # read back one demodulation packet (?)
            ans = yield p.send() #Send the packet to the direct ethernet
            # server parse the packets out and return data. packets is a list
            # of 48-byte strings
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(self.extractDemod(packets,
                self.DEMOD_CHANNELS_PER_PACKET, mode))
            
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
            'trigCount': a[2] + a[3]<<8,
            'nPackets': a[4],
            'badPackets': a[5]
            } 
    
    @staticmethod
    def extractDemod(packets, nDemod, mode):
        """Extract Demodulation data from a list of packets (byte strings).
        
        After demodulation is done on each retrigger, demodulator output is put
        into a FIFO from channel 0 to numchan[7..0]-1.  Once 11 channels are
        in FIFO (44 bytes), or end of all retriggering, the ethernet packet is
        sent by pulling bytes out of FIFO, 44 bytes per output event.  Use
        numchan[7..0]=11 to read back every AD retrigger, since the writing of
        44 bytes will immediately trigger a FIFO read.  

        The FIFO stores 8192 bytes of data, or 186 packets.  This should be fine except for really long sequences.  If you have many retriggers that are closely spaced, with large number channels, the FIFO will overflow before having a chance to release the data.  The total Ethernet transmission time for one packet is around 5 us.  We have halved the averager size to 8 us to have larger FIFO memory.    

        When returning these packets, there is a running count from the end bytes countpack[7..0] and countrb[15..0] that increases for each packet.  This data enables one to check if any packets were missed or to check for their ordering.    

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
        data = ''.join(data[:44] for data in packets)
        pktCounters = [ data[46] for data in packets ]
        readbackCounters = [ data[44] + data[45]<<8 for data in packets ]
        if mode=='iq':
            vals = np.fromstring(data, dtype='<i2') # Convert to 16-bit int array
            # Slowest varying index: time step, next slowest index : demodulator, fastest index: I vs Q
            #  Transpose first two indices to make demodulator first index 
            # Iq0[t=0], Qq0[t=0], Iq1[t=0], Qq1[t=0], Iq0[t=1], Qq0[t=1], Iq1[t=1], Qq1[t=1]
            #    
            #     goes to:
            # data[qubit, time_step, (I=0 | Q=1)]           
            
            data = vals.reshape(-1 , nDemod, 2).astype(int).transpose((1, 0, 2))
            return (data, pktCounters, readbackCounters)
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

fpga.REGISTRY[('ADC', 7)] = ADC_Build7
