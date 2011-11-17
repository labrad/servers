import numpy as np

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.devices import DeviceWrapper
from labrad import types as T

from util import littleEndian, TimedLock


# CHANGELOG
#
# 2011 November 17 - Daniel Sank
# Changed params->buildParams to match with changes in dac.py
#
# 2011 February 9 - Daniel Sank
# Removed almost all references to hardcoded hardware parameters, for example
# the number of demod channels. These values are now board specific and loaded
# by AdcDevice.connect().


# +DOCUMENTATION
#
# ++REGISTRY KEYS
# adcBuildN: *(s?), [(parameterName, value),...]
# Each build of the FPGA code has a build number. We use this build number to
# determine the hardware parameters for each board. Hardware parameters are:
#   DEMOD_CHANNELS - Number of active demod channels
#   DEMOD_CHANNELS_PER_PACKET - Total number of demod channels for which data is returned.
#   DEMOD_PACKET_LEN - Length, in bytes, of demod data packets NOT including length bytes.
#   DEMOD_TIME_STEP - Period, in nanoseconds, of the clock used in demodulation.
#   AVERAGE_PACKETS - Number of packets send back for average mode.
#   AVERAGE_PACKET_LEN - Length, in bytes, of average mode packets NOT including length bytes.
#   TRIG_AMP - Maximum value allowed in trig tables (255)
#   LOOKUP_TABLE_LEN - Number of physical addresses in trig the lookup table.
#   FILTER_LEN - length of filter function
#   SRAM_WRITE_DERPS - Total number of writable derps in SRAM, ie filter and trig tables
#   SRAM_WRITE_PKT_LEN - Number of words written per SRAM write packet, ie. words per derp.



#Constant values accross all boards
REG_PACKET_LEN = 59
READBACK_LEN = 46

RUN_MODE_AVERAGE_AUTO = 2
RUN_MODE_AVERAGE_DAISY = 3
RUN_MODE_DEMOD_AUTO = 4
RUN_MODE_DEMOD_DAISY = 5
RUN_MODE_CALIBRATE = 7

def macFor(board):
    """Get the MAC address of an ADC board as a string."""
    return '00:01:CA:AA:01:' + ('0'+hex(int(board))[2:])[-2:].upper()

def isMac(mac):
    return mac.startswith('00:01:CA:AA:01:')


# functions to register packets for ADC boards

def regPing():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs

def regAdcPllQuery():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 1
    return regs

def regAdcSerial(bits):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 6
    regs[3:6] = littleEndian(bits, 3)
    return regs

def regAdcRecalibrate():
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = 7
    return regs

def regAdcRun(device, mode, reps, filterFunc, filterStretchAt, filterStretchLen, demods, startDelay=0):
    regs = np.zeros(REG_PACKET_LEN, dtype='<u1')
    regs[0] = mode
    regs[1:3] = littleEndian(startDelay, 2) #Daisychain delay
    regs[7:9] = littleEndian(reps, 2)       #Number of repetitions
    
    if len(filterFunc)<=1:
        raise Exception('Filter function must be at least 2')
    regs[9:11] = littleEndian(len(filterFunc)-1, 2)   #Filter function end address. -1 because of zero indexing!
    regs[11:13] = littleEndian(filterStretchAt, 2)  #Stretch address for filter
    regs[13:15] = littleEndian(filterStretchLen, 2) #Filter function stretch length
    
    for i in range(device.buildParams['DEMOD_CHANNELS']):
        if i not in demods:
            continue
        addr = 15 + 4*i
        regs[addr:addr+2] = littleEndian(demods[i]['dPhi'], 2)      #Lookup table step per sample
        regs[addr+2:addr+4] = littleEndian(demods[i]['phi0'], 2)    #Lookup table start address
    return regs

def processReadback(resp):
    a = np.fromstring(resp, dtype='<u1')
    return {
        'build': a[0],
        'noPllLatch': bool(a[1] > 0),
    }

def pktWriteSram(device, derp, data):
    assert 0 <= derp < device.buildParams['SRAM_WRITE_DERPS'], 'SRAM derp out of range: %d' % derp 
    data = np.asarray(data)
    pkt = np.zeros(1026, dtype='<u1')
    pkt[0:2] = littleEndian(derp, 2)
    pkt[2:2+len(data)] = data
    return pkt


# wrapper that actually talks to the device

class AdcDevice(DeviceWrapper):
    """Manages communication with a single GHz ADC board.
    
    All communication happens through the direct ehternet server,
    and we set up one unique context to use for talking to each board.
    """
    
    # lifecycle functions
    
    @inlineCallbacks
    def connect(self, name, group, de, port, board, build):
        """Establish a connection to the board."""
        print 'connecting to ADC board: %s (build #%d)' % (macFor(board), build)

        self.boardGroup = group
        self.server = de
        self.cxn = de._cxn
        self.ctx = de.context()
        self.port = port
        self.board = board
        self.build = build
        self.MAC = macFor(board)
        self.devName = name
        self.serverName = de._labrad_name
        self.timeout = T.Value(1, 's')

        # set up our context with the ethernet server
        p = self.makePacket()
        p.connect(port)
        #p.require_length(70)
        # ADC boards send packets with different lengths:
        # - register readback: 46 bytes
        # - demodulator output: 48 bytes
        # - average readout: 1024 bytes
        p.destination_mac(self.MAC)
        p.require_source_mac(self.MAC)
        #p.source_mac(self.boardGroup.sourceMac)
        p.timeout(self.timeout)
        p.listen()
        yield p.send()
        
        #Get build specific information about this device
        #We talk to the labrad system using a new context and close it when done
        reg = self.cxn.registry
        ctxt = reg.context()
        p = reg.packet()
        p.cd(['','Servers','GHz FPGAs'])
        p.get('adcBuild'+str(self.build))
        try:
            hardwareParams = yield p.send()
            hardwareParams = hardwareParams['get']
            parseBuildParameters(hardwareParams, self)
        finally:
            yield self.cxn.manager.expire_context(reg.ID, context=ctxt)        
    
    @inlineCallbacks
    def shutdown(self):
        """Called when this device is to be shutdown."""
        yield self.cxn.manager.expire_context(self.server.ID, context=self.ctx)
    
    
    # packet creation functions
    
    def makePacket(self):
        """Create a new packet to be sent to the ethernet server for this device."""
        return self.server.packet(context=self.ctx)
    
    def makeFilter(self, data, p):
        """Update a packet for the ethernet server with SRAM commands to upload the filter function."""
        for page in range(4):
            start = self.buildParams['SRAM_WRITE_PKT_LEN'] * page
            end = start + self.buildParams['SRAM_WRITE_PKT_LEN']
            pkt = pktWriteSram(self, page, data[start:end])
            p.write(pkt.tostring())
    
    def makeTrigLookups(self, demods, p):
        """Update a packet for the ethernet server with SRAM commands to upload Trig lookup tables."""
        page = 4
        channel = 0
        while channel < self.buildParams['DEMOD_CHANNELS']:
            data = []
            for ofs in [0, 1]:
                ch = channel + ofs
                for func in ['cosine', 'sine']:
                    if ch in demods:
                        d = demods[ch][func]
                    else:
                        d = np.zeros(self.buildParams['LOOKUP_TABLE_LEN'], dtype='<u1')
                    data.append(d)
            data = np.hstack(data)
            pkt = pktWriteSram(self, page, data)
            p.write(pkt.tostring())            
            channel += 2 # two channels per sram packet
            page += 1 # each sram packet writes one page
    
    def collect(self, nPackets, timeout, triggerCtx):
        """Create a packet to collect data on the FPGA."""
        p = self.makePacket()
        p.timeout(T.Value(timeout, 's'))
        p.collect(nPackets)
        # note that if a timeout error occurs the remainder of the packet
        # is discarded, so that the trigger command will not be sent
        p.send_trigger(triggerCtx)
        return p

    def trigger(self, triggerCtx):
        """Create a packet to trigger the board group context."""
        return self.makePacket().send_trigger(triggerCtx)
    
    def read(self, nPackets):
        """Create a packet to read data from the FPGA."""
        return self.makePacket().read(nPackets)

    def discard(self, nPackets):
        """Create a packet to discard data on the FPGA."""
        return self.makePacket().discard(nPackets)

    def setup(self, filter, demods):
        filterFunc, filterStretchLen, filterStretchAt = filter
        p = self.makePacket()
        self.makeFilter(filterFunc, p)
        self.makeTrigLookups(demods, p)
        amps = ''
        for ch in xrange(self.buildParams['DEMOD_CHANNELS']):
            if ch in demods:
                cosineAmp = demods[ch]['cosineAmp']
                sineAmp = demods[ch]['sineAmp'] 
            else:
                cosineAmp = sineAmp = 0
            amps += '%s,%s;' % (cosineAmp, sineAmp) 
        setupState = '%s: filter=%s, trigAmps=%s' % (self.devName, filterFunc.tostring(), amps)
        return p, setupState

    def clear(self, triggerCtx=None):
        """Create a packet to clear the ethernet buffer for this board."""
        p = self.makePacket().clear()
        if triggerCtx is not None:
            p.send_trigger(triggerCtx)
        return p
    
    
    # board communication (can be called from within test mode)
    
    @inlineCallbacks
    def _sendSRAM(self, filter, demods={}):
        """Write SRAM data to the FPGA."""
        p = self.makePacket()
        self.makeFilter(filter, p)
        self.makeTrigLookups(demods, p)
        yield p.send()
    
    
    @inlineCallbacks
    def _sendRegisters(self, regs, readback=True, timeout=T.Value(10, 's')):
        """Send a register packet and optionally readback the result.

        If readback is True, the result packet is returned as a string of bytes.
        """
        if not isinstance(regs, np.ndarray):
            regs = np.asarray(regs, dtype='<u1')
        p = self.makePacket()
        p.write(regs.tostring())
        if readback:
            p.timeout(timeout)
            p.read()
        ans = yield p.send()
        if readback:
            src, dst, eth, data = ans.read
            returnValue(data)
    
    @inlineCallbacks
    def _runSerial(self, data):
        """Run a command or list of commands through the serial interface."""
        for d in data:
            regs = regAdcSerial(d)
            yield self._sendRegisters(regs, readback=False)
    
    def testMode(self, func, *a, **kw):
        """Run a func in test mode on our board group."""
        return self.boardGroup.testMode(func, *a, **kw)
    
    
    # chatty functions that require locking the device
    
    def recalibrate(self):
        @inlineCallbacks
        def func():
            regs = regAdcRecalibrate()
            yield self._sendRegisters(regs, readback=False)
        return self.testMode(func)
    
    def initPLL(self):
        @inlineCallbacks
        def func():
            yield self._runSerial([0x1FC093, 0x1FC092, 0x100004, 0x000C11])
        return self.testMode(func)
    
    def queryPLL(self):
        @inlineCallbacks
        def func():
            regs = regAdcPllQuery()
            r = yield self._sendRegisters(regs)
            returnValue(processReadback(r)['noPllLatch'])
        return self.testMode(func)

    def buildNumber(self):
        @inlineCallbacks
        def func():
            regs = regPing()
            r = yield self._sendRegisters(regs)
            returnValue(str(processReadback(r)['build']))
        return self.testMode(func)
    
    def runAverage(self, filterFunc, filterStretchLen, filterStretchAt, demods):
        @inlineCallbacks
        def func():
            # build registry packet
            regs = regAdcRun(self, RUN_MODE_AVERAGE_AUTO, 1, filterFunc, filterStretchLen, filterStretchAt, demods)
            
            p = self.makePacket()           # create packet for the ethernet server
            #self.makeFilter(filterFunc, p)  # upload filter function, adds a p.write()
            #self.makeTrigLookups(demods, p) # upload trig lookup tables adds a p.write()
            p.write(regs.tostring())        # send register packet
            p.timeout(T.Value(10, 's'))     # set a conservative timeout
            p.read(self.buildParams['AVERAGE_PACKETS'])         # read back all packets from average buffer
            ans = yield p.send() #Send the packet to the direct ethernet server
                    
            # parse the packets out and return data
            packets = [data for src, dst, eth, data in ans.read]
            returnValue(extractAverage(packets))
            
        return self.testMode(func)

    def runDemod(self, filterFunc, filterStretchLen, filterStretchAt, demods):
        @inlineCallbacks
        def func():
            # build register packet
            regs = regAdcRun(self, RUN_MODE_DEMOD_AUTO, 1, filterFunc, filterStretchLen, filterStretchAt, demods)
    
            # create packet for the ethernet server
            p = self.makePacket()
            self.makeFilter(filterFunc, p) # upload filter function
            self.makeTrigLookups(demods, p) # upload trig lookup tables, cosine and sine for each demod channel
            p.write(regs.tostring()) # send registry packet
            p.timeout(T.Value(10, 's')) # set a conservative timeout
            p.read(1) # read back one demodulation packet
            ans = yield p.send() #Send the packet to the direct ethernet server
            # parse the packets out and return data
            packets = [data for src, dst, eth, data in ans.read] #list of 48-byte strings
            returnValue(extractDemod(packets, self.buildParams['DEMOD_CHANNELS_PER_PACKET']))
            
        return self.testMode(func)

    def runCalibrate(self):
        @inlineCallbacks
        def func():
            # build register packet
            filterFunc=np.zeros(self.buildParams['FILTER_LEN'],dtype='<u1')
            filterStretchLen=0
            filterStretchAt=0
            demods={}
            regs = regAdcRun(self, RUN_MODE_CALIBRATE, 1, filterFunc, filterStretchLen, filterStretchAt, demods)
    
            # create packet for the ethernet server
            p = self.makePacket()
            p.write(regs.tostring()) # send registry packet
            yield p.send() #Send the packet to the direct ethernet server
            returnValue(None)
        return self.testMode(func)

def extractAverage(packets):
    """Extract Average waveform from a list of packets (byte strings)."""
    
    data = ''.join(packets) #Join all byte strings together into one long string
    Is, Qs = np.fromstring(data, dtype='<i2').reshape(-1, 2).astype(int).T
    return (Is, Qs)

def extractDemod(packets, nDemod):
    """Extract Demodulation data from a list of packets (byte strings)."""
    data = ''.join(data[:44] for data in packets)   #stick all data strings in packets together, chopping out last 4 bytes from each string
    vals = np.fromstring(data, dtype='<i2')         #Convert string of bytes into numpy array of 16bit integers. <i2 means little endian 2 byte
    Is, Qs = vals.reshape(-1, 2).astype(int).T      #Is,Qs are numpy arrays like   [I0,I1,...,I_numChannels,    I0,I1,...,I_numChannels]
                                                    #                               1st data run                2nd data run    
    #Parse the IQ data into [(Is ch0, Qs ch0), (Is ch1, Qs ch1),...,(Is chnDemod, Qs chnDemod)]
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

    #(*i,{I} *i{Q})

def parseBuildParameters(parametersFromRegistry, device):
    device.buildParams = dict(parametersFromRegistry)
