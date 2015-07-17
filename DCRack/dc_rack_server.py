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
version = 2.2
description = Control Fastbias and Preamp boards.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""


import labrad
from labrad.devices import DeviceServer, DeviceWrapper
from labrad.errors import Error
from labrad.server import setting
from twisted.internet.defer import inlineCallbacks, returnValue


# map from dac channel names to IDs
CHANNEL_IDS = {
    'A': 0,
    'B': 1,
    'C': 2,
    'D': 3
}

# map from high pass filter names to numeric codes.
HIGH_PASS = {
    'DC': 0,
    '3300': 1,
    '1000': 2,
    '330': 3,
    '100': 4,
    '33': 5,
    '10': 6,
    '3.3': 7
}

# map from low pass filter names to numeric codes.
LOW_PASS = {
    '0': 0,
    '0.22': 1,
    '0.5': 2,
    '1.0': 3,
    '2.2': 4,
    '5': 5,
    '10': 6,
    '22': 7
}

# map from polarity names to numeric codes.
POLARITY = {
    'positive': 0,
    'negative': 1
}

# map from monitor bus name to allowed settings for that bus.
# for each bus, the settings are given as a map from name to numeric code.
BUS_SETTINGS = {
    'Abus0': {
        'A0': 80L,
        'B0': 81L,
        'C0': 82L,
        'D0': 83L
    },
    'Abus1': {
        'A1': 88L,
        'B1': 89L,
        'C1': 90L,
        'D1': 91L
    },
    'Dbus0': {
        'trigA': 64L,
        'trigB': 65L,
        'trigC': 66L,
        'trigD': 67L,
        'Pbus0': 64L,
        'clk': 65L,
        'clockon': 66L,
        'cardsel': 67L,
        'dadata': 68L,
        'done': 69L,
        'strobe': 70L,
        'clk': 71L,
        'clk1': 68L,
        'clk2': 69L,
        'clk3': 70L,
        'clk4': 71L
    },
    'Dbus1': {
        'FOoutA': 72L,
        'FOoutB': 73L,
        'FOoutC': 74L,
        'FOoutD': 75L,
        'foin1': 72L,
        'foin2': 73L,
        'foin3': 74L,
        'foin4': 75L,
        'dasyn': 76L,
        'cardsel': 77L,
        'Pbus0': 78L,
        'Clockon': 79L,
        'on1': 76L,
        'on2': 77L,
        'on3': 78L,
        'on4': 79L
    }
}

# op codes for DAC commands
OP_AUTODETECT = 0x60 # 01100000
OP_REG_WRITE  = 0x80 # 10000000
OP_TRIGGER    = 0xc0 # 11000000
OP_INIT       = 0xc4 # 11000100
OP_STREAM     = 0xc8 # 11001000
OP_LEDS       = 0xe0 # 11100000


class DcRackWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port, cards):
        """Connect to a dc rack device."""
        print 'connecting to "{}" on port "{}"...'.format(server.name, port)
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
            if card[1] == 'preamp':
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
    def write(self, code):
        """Write a data value to the dc rack."""
        yield self.packet().write(code).send()
        print code

    @inlineCallbacks
    def initDACs(self):
        """Initialize the DACs."""
        yield self.write([OP_INIT])
        returnValue(OP_INIT)

    @inlineCallbacks
    def selectCard(self, data):
        """Sends a select card command."""
        self.activeCard = str(data)
        yield self.write([long(data & 0x3f)])
        returnValue(long(data & 0x3f))

    @inlineCallbacks
    def changeHighPassFilter(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        ch = preamp.channels[channel]
        ch.update(highPass=data)
        yield self.sendPreampPacket(channel, ch)
        returnValue(ch.highPass)

    @inlineCallbacks
    def changeLowPassFilter(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        ch = preamp.channels[channel]
        ch.update(lowPass=data)
        yield self.sendPreampPacket(channel, ch)
        returnValue(ch.lowPass)

    @inlineCallbacks
    def changePolarity(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        ch = preamp.channels[channel]
        ch.update(polarity=data)
        yield self.sendPreampPacket(channel, ch)
        returnValue(ch.polarity)

    @inlineCallbacks
    def changeDCOffset(self, channel, data):
        preamp = self.rackCards[self.activeCard]
        ch = preamp.channels[channel]
        ch.update(offset=data)
        yield self.sendPreampPacket(channel, ch)
        returnValue(ch.offset)

    @inlineCallbacks
    def sendPreampPacket(self, channelName, channel):
        ID = CHANNEL_IDS[channelName]

        hp = HIGH_PASS[channel.highPass]
        lp = LOW_PASS[channel.lowPass]
        pol = POLARITY[channel.polarity]
        ofs = channel.offset

        # assemble the full value to be written to the registry
        reg = ((hp & 7) << 21) | ((lp & 7) << 18) | ((pol & 1) << 17) | (ofs & 0xFFFF)

        # write data into registry and then trigger the DAC output
        yield self.write([
            OP_REG_WRITE | ((reg >> 18) & 0x3f),
            OP_REG_WRITE | ((reg >> 12) & 0x3f),
            OP_REG_WRITE | ((reg >>  6) & 0x3f),
            OP_REG_WRITE | ( reg        & 0x3f),
            OP_TRIGGER | ID
        ])

    @inlineCallbacks
    def changeMonitor(self, channel, command, keys=None):
        settings = BUS_SETTINGS[channel]

        if keys is None:
            keys = sorted(settings.keys())

        if command is None:
            returnValue(keys)

        if command not in settings:
            raise Error('Allowed commands: {}.'.format(', '.join(keys)))

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
            data = 4*data[0] + 2*data[1] + 1*data[2]
        else:
            data &= 0x7
        self.write([1L])
        yield self.write([OP_LEDS | data])
        returnValue(data)

    @inlineCallbacks
    def identSelf(self, timeout=1):
        """Sends an identification command."""
        p = self.packet()
        p.timeout()
        p.read()
        p.write([OP_AUTODETECT])
        p.timeout(timeout)
        p.read(1, key='ID')
        p.timeout()
        p.read(key='ID')
        try:
            res = yield p.send()
            returnValue(''.join(res['ID']))
        except:
            raise Exception('Ident error')

    def returnCardList(self):
        cards = []
        for key in self.rackCards.keys():
            if self.rackCards[key] == 'fastbias':
                cards.append([key, 'fastbias'])
            else:
                cards.append([key, 'preamp'])
        return cards

    def preampState(self, cardNumber, channel):
        state = self.rackCards[str(cardNumber)].channels[channel].strState()
        return state

    def getMonitorState(self):
        return self.rackMonitor.monitorState()

    @inlineCallbacks
    def commitToRegistry(self, reg):
        card = self.rackCards[self.activeCard]
        if isinstance(card, Preamp):
            yield reg.cd(['', 'Servers', 'DC Racks', 'Preamps'], True)
            cardName = 'Preamp {}'.format(self.activeCard)
            p = reg.packet()
            def state(chan):
                """Return a tuple of channel state, to be stored in the registry"""
                return (chan.highPass, chan.lowPass, chan.polarity, chan.offset)
            p.set(cardName, (state(card.A), state(card.B), state(card.C), state(card.D)))
            yield p.send()
        else:
            print 'card is not a preamp'

    @inlineCallbacks
    def loadFromRegistry(self, reg):
        card = self.rackCards[self.activeCard]
        if isinstance(card, Preamp):
            yield reg.cd(['', 'Servers', 'DC Racks', 'Preamps'], True)
            cardName = 'Preamp {}'.format(self.activeCard)
            p = reg.packet()
            p.get(cardName, key=cardName)
            result = yield p.send()
            ans = result[cardName]
            def update(chan, state):
                """Update channel state from a tuple stored in the registry"""
                chan.highPass, chan.lowPass, chan.polarity, chan.offset = state[0]
            for i, chan in enumerate([card.A, card.B, card.C, card.D]):
                update(chan, ans[i])
        else:
            print 'card is not a preamp'


    @inlineCallbacks
    def triggerChannel(self, channel):
        """Tell the given channel to pull data from register and update DAC value"""
        ID = CHANNEL_IDS[channel]
        yield self.write([OP_TRIGGER | ID])


    @inlineCallbacks
    def pushRegisterValue(self, dac, slow, voltage):
        """Pushes 18 bits of data into 18 bit shift register.

        High bit is fine(0) or coarse(1) DAC, low bit is fast(0) or slow(1)
        slew rate, and middle 16 bits are voltage value.
        """

        # clip voltage to allowed range
        num = voltage['V']
        if num > 2.5:
            num = 2.5
        elif num < 0 and not dac:
            num = 0
        elif num < -2.5:
            num = -2.5

        # convert voltage into 16-bit number, plus low bit for DAC selection
        if dac:
            dac_value = long(float(num+2.5)/5.0 * 0xffff)
            reg = (dac_value << 1) | 1
        else:
            dac_value = long(float(num)/2.5 * 0xffff)
            reg = (dac_value << 1)

        # set high bit for slew rate
        if slow:
            reg |= 0x20000

        # shift bits into register in groups of 6
        yield self.write([
            OP_REG_WRITE | ((reg >> 12) & 0x3f),
            OP_REG_WRITE | ((reg >> 6) & 0x3f),
            OP_REG_WRITE | ((reg) & 0x3f)
        ])

    @inlineCallbacks
    def setVoltage(self, card, channel, dac, slow, num):
        """Executes sequence of commands to set a voltage value"""
        yield self.selectCard(card)
        yield self.pushRegisterValue(dac, slow, num)
        yield self.triggerChannel(channel)

    @inlineCallbacks
    def streamChannel(self, channel):
        """Command to set channel to take streaming data from GHz DAC"""
        ID = CHANNEL_IDS[channel]
        yield self.write([OP_STREAM | ID])

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
            devName = '{} - {}'.format(server, port)
            devs += [(name, (server, port, cards))]
        returnValue(devs)


    @setting(20, 'Select Card', data='w', returns='w')
    def select_card(self, c, data):
        """Sends a select card command."""
        dev = self.selectedDevice(c)
        card = yield dev.selectCard(data)
        returnValue(card)

    @setting(70, 'init_dacs', returns='w')
    def init_DACs(self, c):
        """Initialize the DACs."""
        dev = self.selectedDevice(c)
        init = yield dev.initDACs()
        returnValue(init)

    @setting(60, 'Change High Pass Filter', channel='s', data='s')
    def change_high_pass_filter(self, c, channel, data):
        """Change high pass filter settings for preamp channel on selected card."""
        dev = self.selectedDevice(c)
        hp = yield dev.changeHighPassFilter(channel, data)
        returnValue(hp)

    @setting(34, 'Change Low Pass Filter', channel='s', data='s')
    def change_low_pass_filter(self, c, channel, data):
        """Change low pass filter settings for preamp channel on selected card."""
        dev = self.selectedDevice(c)
        lp = yield dev.changeLowPassFilter(channel, data)
        returnValue(lp)

    @setting(400, 'Change Polarity', channel='s', data='s')
    def change_polarity(self, c, channel, data):
        """Change polarity of preamp channel on selected card."""
        dev = self.selectedDevice(c)
        pol = yield dev.changePolarity(channel, data)
        returnValue(pol)

    @setting(123, 'change_dc_offset', channel='s', data='w')
    def change_dc_offset(self, c, channel, data): 
        """Change DC offset for preamp channel on selected card."""
        dev = self.selectedDevice(c)
        offset = yield dev.changeDCOffset(channel, data)
        returnValue(offset)

    @setting(130, 'change monitor', channel='s', command='s')
    def change_monitor(self, c, channel, command=None):
        """Change monitor output."""
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
        """List cards configured in the registry (does not query cards directly)."""
        dev = self.selectedDevice(c)
        cards = dev.returnCardList()
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
        self.A = Channel('DC', '0', 'positive', 0)
        self.B = Channel('DC', '0', 'positive', 0)
        self.C = Channel('DC', '0', 'positive', 0)
        self.D = Channel('DC', '0', 'positive', 0)
        self.channels = {'A': self.A, 'B': self.B, 'C': self.C, 'D': self.D}


class Channel:
    def __init__(self, hp, lp, pol, ofs):
        self.highPass = hp
        self.lowPass = lp
        self.polarity = pol
        self.offset = ofs

    def update(self, highPass=None, lowPass=None, polarity=None, offset=None):
        """Update channel parameter(s) to the given values.

        Before updating a given parameter, we check that it is valid by
        looking it up in the appropriate map from name to code (for highPass,
        lowPass, and polarity) or converting to an int (for offset).
        """
        if highPass is not None:
            HIGH_PASS[highPass]
            self.highPass = highPass

        if lowPass is not None:
            LOW_PASS[lowPass]
            self.lowPass = lowPass

        if polarity is not None:
            POLARITY[polarity]
            self.polarity = polarity

        if offset is not None:
            self.offset = int(offset)

    def state(self):
        """Returns the channel state as a tuple (str, str, str, int)"""
        return (self.highPass, self.lowPass, self.polarity, self.offset)

    def strState(self):
        """Returns the channel state as a list of strings"""
        s = list(self.state)
        s[-1] = str(s[-1])
        return s


class Monitor:
    def __init__(self):
        self.dBus0 = ['0', 'null']
        self.dBus1 = ['0', 'null']
        self.aBus0 = ['0', 'null']
        self.aBus1 = ['0', 'null']
        self.busses = {'Abus0': self.aBus0, 'Abus1': self.aBus1, 'Dbus0': self.dBus0, 'Dbus1': self.dBus1}

    def updateBus(self, bus, card, newState):
        card = str(card)
        self.busses[bus][0] = card
        if card == '0':
            self.busses[bus][1] = 'null'
        else:
            self.busses[bus][1] = newState

    def monitorState(self):
        return [self.dBus0, self.dBus1, self.aBus0, self.aBus1]


TIMEOUT = 1 * labrad.units.s

__server__ = DcRackServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
