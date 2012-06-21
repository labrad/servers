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
name = Cold Switch Server
version = 1.1
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.types import Value
from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import LabradServer, setting
from labrad.errors import Error
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad import util

    
class ColdSwitchWrapper(DeviceWrapper):
    
    @inlineCallbacks
    def connect(self, server, port, oldState):
        """Connect to a cold switch board."""
        print 'connecting to "%s" on port "%s"...' % (server.name, port),
        self.state = oldState
        self.setTrace = []
        self.resetTrace = []
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(1200L)
        p.stopbits(1L)
        p.bytesize(8L)
        p.parity('N')
        p.read() # clear out the read buffer
        p.timeout(TIMEOUT)
        yield p.send()
        self.changeAppliedVoltage(oldState[3])
        print 'done.'
        
    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)
    
    def shutdown(self):
        """Disconnect from the serial port when we shut down."""
        return self.packet().close().send()
    
    @inlineCallbacks
    def write(self, code, index = 0):
        """Write a data value to the cold switch."""
        p = self.packet()
        p.write(code)
        yield p.send()
        
        
    @inlineCallbacks
    def setPulse(self):
        """Send a set command to the cold switch and check
           the current output to see that it set"""
        output = ''
        self.setTrace = []
        p = self.packet()
        p.write('S')
        p.read_line()
        ans = yield p.send()
        output = ans.read_line
        for s in range(len(output)):
                current = 4.0*ord(output[s])*(5.0/4095.0)/10.0
                self.setTrace.append(current)


    @inlineCallbacks
    def resetPulse(self):
        """Send a reset command to the cold switch and check
           the current output to see that it reset"""
        output = ''
        self.resetTrace = []
        p = self.packet()
        p.write('R')
        p.read_line()
        ans = yield p.send()
        output = ans.read_line
        for s in range(len(output)):
                current = 4.0*ord(output[s])*(5.0/4095.0)/10.0
                self.resetTrace.append(current)
    
    
    @inlineCallbacks
    def changeAppliedVoltage(self, voltage):
        """Change the voltage applied during set or reset pulse"""
        voltValues = {'0':'0','1':'1','2':'2','3':'3',
                      '4':'4','5':'5','6':'6','7':'7',
                      '8':'8','9':'9','10':':','11':';',
                      '12':'<','13':'=','14':'>','15':'?'}
        yield self.write(voltValues[str(voltage)])
        self.state[3] = str(voltage)
        returnValue(voltValues[str(voltage)])
    
    @inlineCallbacks    
    def setFirstSwitchChannel(self, channel, commands):
        """change the channel set on the first switch"""
        chan = str(channel)
        if self.state[0]!=chan and chan!='0':
            if self.state[0]!='0':
                reschan = commands[self.state[0]]
                yield self.write(reschan)
                yield self.resetPulse()
                yield util.wakeupCall(1)
            setchan = commands[chan]
            yield self.write(setchan)
            yield self.setPulse()
            yield util.wakeupCall(1)
            self.state[0] = chan
            
        if chan=='0':
            reschan = commands[self.state[0]]
            yield self.write(reschan)
            yield self.resetPulse()
            self.state[0] = chan
        
        returnValue(chan)
    
    @inlineCallbacks    
    def setSecondSwitchChannel(self, channel, commands):
        """change the channel set on the second switch"""
        chan = str(channel)
        if self.state[1]!=chan and chan!='0':
            if self.state[1]!='0':
                reschan = commands[self.state[1]]
                yield self.write(reschan)
                yield self.resetPulse()
                yield util.wakeupCall(1)
            setchan = commands[chan]
            yield self.write(setchan)
            yield self.setPulse()
            yield util.wakeupCall(1)
            self.state[1] = chan
            
        if chan=='0':
            reschan = commands[self.state[1]]
            yield self.write(reschan)
            yield self.resetPulse()
            self.state[1] = chan
            
        returnValue(chan)
    
    @inlineCallbacks        
    def setThirdSwitchChannel(self, channel, commands):
        """change the channel set on the third switch"""
        chan = str(channel)
        if self.state[2]!=chan and chan!='0':
            if self.state[2]!='0':
                reschan = commands[self.state[2]]
                yield self.write(reschan)
                yield self.resetPulse()
                yield util.wakeupCall(1)
            setchan = commands[chan]
            yield self.write(setchan)
            yield self.setPulse()
            yield util.wakeupCall(1)
            self.state[2] = chan
            
        if chan=='0':
            reschan = commands[self.state[2]]
            yield self.write(reschan)
            yield self.resetPulse()
            self.state[2] = chan
            
        returnValue(chan)
            
    @inlineCallbacks 
    def getSetTrace(self):
        """Check the current values of the last set or reset pulse"""
        returnValue(self.setTrace)
    
    @inlineCallbacks 
    def getResetTrace(self):
        """Check the current values of the last set or reset pulse"""
        returnValue(self.resetTrace)

    @inlineCallbacks
    def getSwitchState(self):
        switchState = self.state
        returnValue(switchState)
        
    @inlineCallbacks
    def masterReset(self, switch, commands):
        for command in commands:
            reschan = commands[command]
            yield self.write(reschan)
            yield self.resetPulse()
            yield util.wakeupCall(2)
        self.state[switch] = '0'
    
    @inlineCallbacks
    def updateRegistry(self, reg)
        yield reg.cd(['', 'Servers', 'Cold Switch', 'Links'], True)
        p = reg.packet()
        p.set(self.name,(self.server,self.port,self.state))
        yield p.send()
    
      
        
        
        
class ColdSwitchServer(DeviceServer):
    deviceName = 'Cold Switch Server'
    name = 'Cold Switch Server'
    deviceWrapper = ColdSwitchWrapper
    
    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print 'done.'
        yield DeviceServer.initServer(self)
    
    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.reg
        yield reg.cd(['', 'Servers', 'Cold Switch', 'Links'], True)
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
        for name, (server, port, oldState) in self.serialLinks.items():
            if server not in self.client.servers:
                continue
            server = self.client[server]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (server, port)
            devs += [(name, (server, port, oldState))]
        returnValue(devs)
         
    @setting(456, 'change voltage', data='w', returns='s')
    def change_voltage(self, c, data):
        """Changes the voltage applied to set or reset the switch"""
        dev = self.selectedDevice(c)
        reg = self.client.registry()
        voltage = yield dev.changeAppliedVoltage(data)
        yield dev.updateRegistry(self.reg)
        returnValue(voltage)
        
    @setting(457, 'set switch1', data='w', returns='s')
    def set_switch1(self, c, data):
        """Changes which port on switch one is connected to the output"""
        commandList =[{'1':'a','2':'b','3':'c','4':'d','5':'e','6':'f'},
              {'1':'g','2':'h','3':'i','4':'j','5':'k','6':'l'},
              {'1':'m','2':'n','3':'o','4':'p','5':'q','6':'r'}]
        dev = self.selectedDevice(c)
        reg = self.client.registry()
        if dev.state[0]== 'null':
            returnValue('null')
        else:
            channel =  yield dev.setFirstSwitchChannel(data, commandList[0])
            yield dev.updateRegistry(self.reg)
            returnValue(channel)
    
    @setting(458, 'set switch2', data='w', returns='s')
    def set_switch2(self, c, data):
        """Changes which port on switch two is connected to the output"""
        commandList =[{'1':'a','2':'b','3':'c','4':'d','5':'e','6':'f'},
              {'1':'g','2':'h','3':'i','4':'j','5':'k','6':'l'},
              {'1':'m','2':'n','3':'o','4':'p','5':'q','6':'r'}]
        dev = self.selectedDevice(c)
        if dev.state[1]== 'null':
            returnValue('null')
        else:
            channel = yield dev.setFirstSwitchChannel(data, commandList[1])
            yield dev.updateRegistry(self.reg)
            returnValue(channel)
    
    @setting(459, 'set switch3', data='w', returns='s')
    def set_switch3(self, c, data):
        """Changes which port on switch three is connected to the output"""
        commandList =[{'1':'a','2':'b','3':'c','4':'d','5':'e','6':'f'},
              {'1':'g','2':'h','3':'i','4':'j','5':'k','6':'l'},
              {'1':'m','2':'n','3':'o','4':'p','5':'q','6':'r'}]
        dev = self.selectedDevice(c)
        if dev.state[2]== 'null':
            returnValue('null')
        else:
            channel = yield dev.setFirstSwitchChannel(data, commandList[2])
            yield dev.updateRegistry(self.reg)
            returnValue(channel)
    
    @setting(461, 'get set trace')
    def get_set_trace(self, c):
        """Returns a trace of the current going through the solenoid for the last switch set command"""
        dev = self.selectedDevice(c)
        currents = yield dev.getSetTrace()
        returnValue(currents)
    
    @setting(462, 'get reset trace')
    def get_reset_trace(self, c):
        """Returns a trace of the current going through the solenoid for the last switch reset command"""
        dev = self.selectedDevice(c)
        currents = yield dev.getResetTrace()
        returnValue(currents)

    @setting(466, 'get switch state', returns = '*s')
    def get_swtich_state(self, c):
        """Returns the current channel for each switch and the current applied voltage"""
        dev = self.selectedDevice(c)
        state = yield dev.getSwitchState()
        returnValue(state)
    
    @setting(467, 'master reset', data = 'w')
    def master_reset(self, c, data):
        """Ensures that all channels for a given switch are disconnected"""
        commandList =[{'1':'a','2':'b','3':'c','4':'d','5':'e','6':'f'},
                      {'1':'g','2':'h','3':'i','4':'j','5':'k','6':'l'},
                      {'1':'m','2':'n','3':'o','4':'p','5':'q','6':'r'}]
        switch = data-1
        dev = self.selectedDevice(c)
        if dev.state[switch]== 'null':
            returnValue('null')
        else:
            yield dev.masterReset(switch, commandList[switch])
            yield dev.updateRegistry(self.reg)
    

TIMEOUT = 1

__server__ = ColdSwitchServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
    
