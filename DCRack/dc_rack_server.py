# Copyright (C) 2011  Ted White
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
### BEGIN NODE INFO
[info]
name = DC Rack Server
version = 2.1
description = Control Fastbias and Preamp boards.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""



from labrad.types import Value
from labrad.units import s
from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import LabradServer, setting
from labrad.errors import Error
from twisted.internet.defer import inlineCallbacks, returnValue

class NoConnectionError(Error):
    """You need to connect first."""
    code = 2


class DcRackWrapper(DeviceWrapper):
    
    @inlineCallbacks
    def connect(self, server, port, cards):
        """Connect to a dc rack device."""
        print 'connecting to "%s" on port "%s"...' % (server.name, port)
        self.rackCards = {}
        self.rackMonitor = Monitor()
        self.activeCard = 100
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(115200L)
        p.read() # clear out the read buffer
        p.timeout(TIMEOUT)
        yield p.send()
        for card in cards:
            if card[1]=='preamp':
                self.rackCards[card[0]] = Preamp()
            else:
                self.rackCards[card[0]] = 'fastbias'
        print 'done.'
    
    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)
    
    def shutdown(self):
        """Disconnect from the serial port when we shut down."""
        return self.packet().close().send()

    @inlineCallbacks
    def write(self, code, index=0):
        """Write a data value to the dc rack."""
        yield self.packet().write(code).send()
        print code

    @inlineCallbacks
    def InitDACs(self):
        """Initialize the DACs."""
        yield self.write([196])
        returnValue(196L)
     
    @inlineCallbacks
    def selectCard(self, data):
        """Sends a select card command."""
        self.activeCard = str(data)
        yield self.write([long(data&63)])
        returnValue(long(data&63))

    @inlineCallbacks
    def changeHighPassFilter(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        lp = preamp.channels[channel].lowPass
        pol = preamp.channels[channel].polarity
        off = preamp.channels[channel].offset
        preamp.updateChannel(channel,data,lp,pol,off)
        hp = yield self.sendChannelPacket(channel,data,lp,pol,off)
        returnValue(hp)


    @inlineCallbacks
    def changeLowPassFilter(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        hp = preamp.channels[channel].highPass
        pol = preamp.channels[channel].polarity
        off = preamp.channels[channel].offset
        preamp.updateChannel(channel,hp,data,pol,off)
        lp = yield self.sendChannelPacket(channel,hp,data,pol,off)
        returnValue(lp)

    @inlineCallbacks
    def changePolarity(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        hp = preamp.channels[channel].highPass
        lp = preamp.channels[channel].lowPass
        off = preamp.channels[channel].offset
        preamp.updateChannel(channel,hp,lp,data,off)
        pol = yield self.sendChannelPacket(channel,hp,lp,data,off)
        returnValue(pol)

    @inlineCallbacks
    def changeDCOffset(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        hp = preamp.channels[channel].highPass
        lp = preamp.channels[channel].lowPass
        pol = preamp.channels[channel].polarity
        preamp.updateChannel(channel,hp,lp,pol,data)
        offset = yield self.sendChannelPacket(channel,hp,lp,pol,data)
        returnValue(offset)
        
    @inlineCallbacks
    def sendChannelPacket(self, channel, hp, lp, pol, off):
        command = []          
        command.append({'DC':0,'3300':1,'1000':2,'330':3,'100':4,'33':5,'10':6,'3.3':7}[hp])
        command.append({'0':0,'0.22':1,'0.5':2,'1.0':3,'2.2':4,'5':5,'10':6,'22':7}[lp])
        command.append({'positive':0,'negative':1}[pol])
        command.append(off)
        tupleCommand = (command[0]&7,command[1]&7,command[2]&1,command[3]&0xFFFF)
        ID = {'A':192L,'B':193L,'C':194L,'D':195L}[channel]
        data = ((tupleCommand[0] & 7) << 21) | \
                ((tupleCommand[1] & 7) << 18)| \
                ((tupleCommand[2] & 1) << 17)| \
                (tupleCommand[3] & 0xFFFF)
        L = [(data >> 18) & 0x3f | 0x80,
             (data >> 12) & 0x3f | 0x80,
             (data >>  6) & 0x3f | 0x80,
              data        & 0x3f | 0x80,
             (ID)]
        yield self.write(L)
        returnValue(data)
        
    @inlineCallbacks
    def changeMonitor(self, channel, command, keys = None):
        ID = {'Abus0':0,'Abus1':1,'Dbus0':2,'Dbus1':3}[channel]
        settings = [{'A0': 80L, 'B0': 81L, 'C0': 82L, 'D0': 83L},
                    {'A1': 88L, 'B1': 89L, 'C1': 90L, 'D1': 91L},
                    {'trigA':  64L, 'trigB': 65L, 'trigC':  66L, 'trigD': 67L,
                     'Pbus0': 64L, 'clk':  65L, 'clockon': 66L, 'cardsel':  67L,
                     'dadata': 68L, 'done':  69L, 'strobe': 70L, 'clk': 71L,
                     'clk1': 68L, 'clk2': 69L, 'clk3':  70L, 'clk4': 71L},
                    {'FOoutA': 72L, 'FOoutB':  73L, 'FOoutC': 74L, 'FOoutD':  75L,
                     'foin1':  72L, 'foin2': 73L, 'foin3':  74L, 'foin4': 75L,
                     'dasyn':  76L, 'cardsel': 77L, 'Pbus0':  78L, 'Clockon': 79L,
                     'on1': 76L, 'on2':  77L, 'on3': 78L, 'on4': 79L}][ID]
        if keys is None:
            keys = sorted(settings.keys())

        if command is None:
            returnValue(keys)

        if command not in settings:
            raise Error('Allowed commands: %s.' % ', '.join(keys))

        self.rackMonitor.updateBus(channel, self.activeCard, command)
        change = yield self.sendMonitorPacket(command, settings)
        returnValue(change)
        
    @inlineCallbacks
    def sendMonitorPacket(self, command, settings):
        com = settings[command]
        yield self.write([com])
        returnValue(com)
        
        
    @inlineCallbacks
    def changeLEDs(self, data):
        """Sets LED status."""
        if isinstance(data, tuple):
            data = 224 + 4*data[0] + 2*data[1] + 1*data[2]
        else:
            data = 224 + (data & 7)
        self.write([1L])
        yield self.write([data])
        returnValue(data & 7)

    @inlineCallbacks
    def identSelf(self, timeout=1):
        """Sends an identification command."""
        p = self.packet()
        p.timeout()
        p.read()
        p.write([96L])
        p.timeout(timeout)
        p.read(1, key = 'ID')
        p.timeout()
        p.read(key = 'ID')
        try:
            res = yield p.send()
            returnValue(''.join(res['ID']))
        except:
            raise Exception('Ident error')

    def returnCardList(self):
        returnList = []
        for key in self.rackCards.keys():
            if self.rackCards[key]=='fastbias':
                returnList.append([key, 'fastbias'])
            else:
                returnList.append([key, 'preamp'])
        return returnList

    @inlineCallbacks
    def preampState(self, cardNumber, channel):
        state = self.rackCards[str(cardNumber)].preampChannelState(channel)
        returnValue(state)

    @inlineCallbacks
    def getMonitorState(self):
        state = self.rackMonitor.monitorState()
        returnValue(state)
        
    @inlineCallbacks
    def commitToRegistry(self, reg):
        card = self.rackCards[self.activeCard]
        if isinstance(card, Preamp):
            yield reg.cd(['', 'Servers', 'DC Racks', 'Preamps'], True)
            cardName = 'Preamp ' + str(self.activeCard)
            p = reg.packet()
            p.set(cardName,((card.A.highPass, card.A.lowPass, card.A.polarity, card.A.offset),
                             (card.B.highPass, card.B.lowPass, card.B.polarity, card.B.offset),
                             (card.C.highPass, card.C.lowPass, card.C.polarity, card.C.offset),
                             (card.D.highPass, card.D.lowPass, card.D.polarity, card.D.offset)))
            yield p.send()
        else:
            print 'card is not a preamp'
    
    @inlineCallbacks
    def loadFromRegistry(self, reg):
        card = self.rackCards[self.activeCard]
        if isinstance(card, Preamp):
            yield reg.cd(['', 'Servers', 'DC Racks', 'Preamps'], True)
            cardName = 'Preamp ' + str(self.activeCard)
            p = reg.packet()
            p.get(cardName, key = cardName)
            result = yield p.send()
            ans = result[cardName]
            card.A.highPass = ans[0][0]
            card.A.lowPass = ans[0][1]
            card.A.polarity = ans[0][2] 
            card.A.offset = ans[0][3]
            card.B.highPass = ans[1][0]
            card.B.lowPass = ans[1][1]
            card.B.polarity = ans[1][2]
            card.B.offset = ans[1][3]
            card.C.highPass = ans[2][0]
            card.C.lowPass = ans[2][1]
            card.C.polarity = ans[2][2]
            card.C.offset = ans[2][3]
            card.D.highPass = ans[3][0]
            card.D.lowPass = ans[3][1]
            card.D.polarity = ans[3][2]
            card.D.offset = ans[3][3]
        else:
            print 'card is not a preamp'


    @inlineCallbacks
    def triggerChannel(self, channel):
        """Tells selected channel to pull data from registry and update DAC value"""
        ChannelID = {'A':0, 'B':1, 'C':2, 'D':3}[channel]
        #Bitwise OR with 11000000
        yield self.write([192|ChannelID])


    @inlineCallbacks
    def pushRegistryValue(self, dac, slow, voltage):
        """Pushes 18 bits of data into 18 bit shift register. First bit is fine(0) or coarse(1) DAC, 
        last bit is fast(0) or slow(1) slew rate, and middle 16 bits are voltage value"""
        #Conversion of voltage value into 16-bit number, plus bits for DAC selection and slew rate
        num = voltage['V']
        if num > 2.5:
            num = 2.5
        elif num < 0 and not dac:
            num = 0
        elif num < -2.5:
            num = -2.5
        if dac:
            intNum = long(float(num+2.5)/5.0 * 65535)
            intNum = (intNum << 1)|1
            if slow:
                intNum = intNum|131702
        else:
            intNum = long(float(num)/2.5 * 65535)
            intNum = (intNum << 1)
            if slow:
                intNum = intNum|131702
                
        #Push bits to proper positions
        Byte1 = long(intNum)
        Byte2 = long(intNum>>6)
        Byte3 = long(intNum>>12)

        #Write 8 bit sequences
        yield self.write([128|(Byte3&63)])
        yield self.write([128|(Byte2&63)])
        yield self.write([128|(Byte1&63)])
        
    @inlineCallbacks
    def setVoltage(self, card, channel, dac, slow, num):
        """Executes sequence of commands to set a voltage value"""
        yield self.selectCard(card)
        yield self.pushRegistryValue(dac, slow, num)
        yield self.triggerChannel(channel)

        
    @inlineCallbacks
    def streamChannel(self, channel):
        """Command to set channel to take streaming data from GHz DAC"""
        ChannelID = {'A':0, 'B':1, 'C':2, 'D':3}[channel]
        #Bitwise OR with 11001000
        long(ChannelID)
        yield self.write([200|ChannelID])

    @inlineCallbacks
    def setChannelStream(self, card, channel):
        """Executes sequence of commands to set channel to streaming mode"""
        yield self.selectCard(card)
        yield self.streamChannel(channel)


class DcRackServer(DeviceServer):
    deviceName = 'DC Rack Server'
    name = 'DC Rack Server'
    deviceWrapper = DcRackWrapper

    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        yield self.loadConfigInfo()
        print 'done.'
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.client.registry()
        yield reg.cd(['', 'Servers', 'DC Racks', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        for k in keys:
            p.get(k, key=k)
        ans = yield p.send()
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        """Find available devices from list stored in the registry."""
        devs = []
        for name, (server, port, cards) in self.serialLinks.items():
            if server not in self.client.servers:
                continue
            server = self.client[server]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (server, port)
            devs += [(name, (server, port, cards))]
        returnValue(devs)

    
    @setting(20, 'Select Card', data='w', returns='w')
    def select_card(self, c, data):
        """Sends a select card command."""
        dev = self.selectedDevice(c)
        card = yield dev.selectCard(data)
        returnValue(card)

    @setting(70, 'init_dacs', returns='w')
    def Init_DACs(self, c):
        """Initialize the DACs."""
        dev = self.selectedDevice(c)
        init = yield dev.InitDACs()
        returnValue(init)

    @setting(60, 'Change High Pass Filter',channel = 's', data = 's')
    def change_high_pass_filter(self, c, channel, data):
        """
        Change high pass filter settings for preamp channel on selected card.
        """
        dev = self.selectedDevice(c)
        hp = yield dev.changeHighPassFilter(channel, data)
        returnValue(hp)

    @setting(34, 'Change Low Pass Filter',channel = 's', data = 's')
    def change_low_pass_filter(self, c, channel, data):
        """
        Change low pass filter settings for preamp channel on selected card.
        """
        dev = self.selectedDevice(c)
        lp = yield dev.changeLowPassFilter(channel, data)
        returnValue(lp)

    @setting(400, 'Change Polarity',channel = 's', data = 's')
    def change_polarity(self, c, channel, data):
        """
        Change polarity of preamp channel on selected card.
        """
        dev = self.selectedDevice(c)
        pol = yield dev.changePolarity(channel, data)
        returnValue(pol)

    @setting(123, 'change_dc_offset', channel = 's', data ='w')
    def change_dc_offset(self, c, channel, data): 
        """
        Change DC offset for preamp channel on selected card.
        """
        dev = self.selectedDevice(c)
        offset = yield dev.changeDCOffset(channel, data)
        returnValue(offset)

    @setting(130, 'change monitor', channel = 's', command = 's')
    def change_monitor(self, c, channel, command=None):
        """
        Change monitor output.
        """
        dev = self.selectedDevice(c)
        change = yield dev.changeMonitor(channel, command)
        returnValue(change)
        
    @setting(336, 'leds',
                 data=['w: Lowest 3 bits: LED flags',
                       '(bbb): Status of BP LED, FP FOout flash, FP Reg. Load Flash'],
                 returns='w')
    def LEDs(self, c, data):
        """Sets LED status."""
        dev = self.selectedDevice(c)
        p = yield dev.changeLEDs(data)
        returnValue(p)


    @setting(893, 'Ident', returns='s')
    def ident(self, c):
        dev = self.selectedDevice(c)
        ident = yield dev.identSelf()
        returnValue(ident)

    @setting(565, 'list_cards')
    def list_cards(self, c):
        """
        List cards configured in the registry (does not query cards directly)
        """
        dev = self.selectedDevice(c)
        cards = yield dev.returnCardList()
        returnValue(cards)

    @setting(455, 'get_preamp_state')
    def getPreampState(self, c, cardNumber, channel):
        dev = self.selectedDevice(c)
        state = yield dev.preampState(cardNumber, channel)
        returnValue(state)

    @setting(423, 'get_monitor_state')
    def getMonitorState(self, c):
        dev = self.selectedDevice(c)
        state = yield dev.getMonitorState()
        returnValue(state)
    
    @setting(867, 'commit_to_registry')
    def commit_to_registry(self, c):
        dev = self.selectedDevice(c)
        reg = self.client.registry()
        yield dev.commitToRegistry(reg)
    
    @setting(868, 'load_from_registry')      
    def load_from_registry(self, c):
        dev = self.selectedDevice(c)
        reg = self.client.registry()
        yield dev.loadFromRegistry(reg)
      
    @setting(874, 'channel_set_voltage', card='w', channel='s', dac='w{0=Fine (unipolar), 1=Coarse (bipolar)}', slow='w', value='v[V]')
    def channel_set_voltage(self, c, card, channel, dac, slow, value):
        """Executes sequence of commands to set a voltage value.
        card: the card ID (according to DIP switches on the PCB)
        channel: A, B, C, or D
        dac: 0 for FINE (unipolar 0..2.5 V) , 1 for COARSE (bipolar -2.5V to +2.5V)
        slow: always 1 with FINE.  For coarse, set the RC time constant
        value: set voltage.  Will be coerced into range for the selected DAC
        """
        dev = self.selectedDevice(c)
        yield dev.setVoltage(card, channel, dac, slow, value)
    
        
    @setting(875, 'channel_stream')
    def channel_stream(self, c, card, channel):
        """Executes sequence of commands to set a channel to streaming mode"""
        dev = self.selectedDevice(c)
        yield dev.setChannelStream(card, channel)
        

class Preamp:
    def __init__(self):
        self.A = Channel('DC','0','positive',0)
        self.B = Channel('DC','0','positive',0)
        self.C = Channel('DC','0','positive',0)
        self.D = Channel('DC','0','positive',0)
        self.channels = {'A':self.A,'B':self.B,'C':self.C,'D':self.D}

    def updateChannel(self,ch,hp,lp,pol,off):
        channel = self.channels[ch]
        channel.highPass = hp
        channel.lowPass = lp
        channel.polarity = pol
        channel.offset = off

    def preampChannelState(self, channel):
        ch = self.channels[channel]
        state = [ch.highPass, ch.lowPass, ch.polarity, str(ch.offset)]
        returnValue(state)

class Channel:
    def __init__(self,w,x,y,z):
        self.highPass = w
        self.lowPass = x
        self.polarity = y
        self.offset = z
        
        

class Monitor:
    def __init__(self):
        self.dBus0 = ['0','null']
        self.dBus1 = ['0','null']
        self.aBus0 = ['0','null']
        self.aBus1 = ['0','null']
        self.busses = {'Abus0':self.aBus0,'Abus1':self.aBus1,'Dbus0':self.dBus0,'Dbus1':self.dBus1}

    def updateBus(self, bus, card, newState):
        card = str(card)
        self.busses[bus][0] = card
        if card == '0':
            self.busses[bus][1] = 'null'
        else:
            self.busses[bus][1] = newState

    def monitorState(self):
        state = []
        state.append(self.dBus0)
        state.append(self.dBus1)
        state.append(self.aBus0)
        state.append(self.aBus1)
        return state

        
TIMEOUT = 1*s

__server__ = DcRackServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
