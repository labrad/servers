"""
"""
import numpy as np

import fpga

# named functions
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock

class ADC_B2(fpga.ADC):
    """ADC build 2"""
    
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
    
    # Methods to get bytes to be written to register
    
    @classmethod
    def regRun(cls, mode, reps, filterFunc, filterStretchAt,
                  filterStretchLen, demods, startDelay=0):
        """Returns a numpy array of register bytes to run the board"""
        regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
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
        derp = 4
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
    def _sendSRAM(self, filter, demods={}):
        """Write filter and sine table SRAM to the FPGA."""
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        yield p.send()
    
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

    def runAverage(self, filterFunc, filterStretchLen, filterStretchAt,
                   demods):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = self.regRun(RUN_MODE_AVERAGE_AUTO, 1, filterFunc,
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
    def processReadback(resp):
        """Process byte string returned by ADC register readback
        
        Returns a dict with following keys
            build - int: the build number of the board firmware
            noPllLatch - bool: True is unlatch, False is latch (I think)
            executionCounter - int: Number of executions since last start
        """
        a = np.fromstring(resp, dtype='<u1')
        return {
            'build': a[0],
            'noPllLatch': bool(a[1] > 0),
            'executionCounter': (a[3]<<8) + a[2]
        }
    
    @staticmethod
    def extractAverage(packets):
        """Extract Average waveform from a list of packets (byte strings)."""
        
        data = ''.join(packets)
        Is, Qs = np.fromstring(data, dtype='<i2').reshape(-1, 2).astype(int).T
        return (Is, Qs)
    
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

fpga.REGISTRY[('ADC', 2)] = ADC_B2


class ADC_B4(fpga.ADC):
    
    # Build-specific constants
    DEMOD_CHANNELS = 4
    DEMOD_CHANNELS_PER_PACKET = 11
    DEMOD_PACKET_LEN = 
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
    
    # Methods to get bytes to be written to register
    
    @classmethod
    def regRun(cls, ...):
        stuff
    
    # Direct ethernet server packet creation methods
    
    def setup(self, ...):
        stuff
    
    @classmethod
    def makeDemodTriggers(cls, )