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
#

"""
### BEGIN NODE INFO
[info]
name = Agilent 8720ES Server
version = 1.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, errors
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from struct import unpack
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad import util
from numpy import array, transpose, linspace, hstack
from time import sleep

class Agilent_8720ES_Wrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        yield self.write("ELED 0 NS") # Zero electrical delay

class Agilent_8720ES_Server(GPIBManagedServer):
    name = 'Agilent 8720ES Server'
    deviceName = 'HEWLETT PACKARD 8720ES'
    deviceWrapper = Agilent_8720ES_Wrapper
    
    @setting(345, 'Get Trace', measured=['b'])
    def get_trace(self, c, measured=False):    
        def parseData(data):
            data = data.split('\n')
            for i in range(len(data)):
                stuff = data[i].split(',')
                num1 = float(stuff[0])
                num2 = float(stuff[1])
                #num = (num1**2 + num2**2)
                #num = 10*np.log10(num)
                # num1 is real, num2 is imaginary
                # units is U (dimensionless... Vout/Vin)
                data[i] = [num1, num2]
            return data
        dev = self.selectedDevice(c)
        if not measured:
            time = yield dev.query('SWET?').addCallback(float)        
            yield dev.write('FORM4') # Set the output format 
            yield dev.write('SING') # Perform a single sweep
            sleep(2*time) # avoid timeout error
        yield dev.write('SMIC')
        result = yield dev.query('OUTPFORM') # Get the data
        data = parseData(result)
        data = array(data)
        start_freq = yield self.start_frequency(c)
        stop_freq = yield self.stop_frequency(c)
        num_point = yield self.num_points(c)
        freqs = linspace(start_freq, stop_freq, num_point)
        data = hstack((transpose([freqs]),data))
        
        returnValue(data)
    
    @setting(346, 'Start Frequency', f=['v[MHz]'], returns=['v[MHz]'])
    def start_frequency(self, c, f=None):
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('STAR %.2f MHZ' % f)
        f = yield dev.query('STAR?').addCallback(float)
        f = T.Value(f, 'Hz')
        returnValue(f)
        
    @setting(347, 'Stop Frequency', f=['v[MHz]'], returns=['v[MHz]'])
    def stop_frequency(self, c, f=None):
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('STOP %.2f MHZ' % f)
        f = yield dev.query('STOP?').addCallback(float)
        f = T.Value(f, 'Hz')
        returnValue(f)
        
    @setting(348, 'Get Maximum')
    def get_max_point(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('SING')
        yield dev.write('SEAMAX')
        result = yield dev.query('OUTPMARK')
        result = result.split(',')
        data = [float(result[0]), float(result[2])]
        returnValue(data)
        
        
    @setting(349, 'Sweep Mode', m=['s'], returns=['s'])
    def sweep_mode(self, c, m=None):
        dev = self.selectedDevice(c)
        modes = ['S11', 'S12', 'S21', 'S22']
        if m is not None:
            m = m.upper()
            if m not in modes:
                raise Exception("Invalid mode")
            yield dev.write(m)
        else:
            for s in modes:
                sbool = yield dev.query(s+'?').addCallback(int).addCallback(bool)
                if sbool:
                    m = s
        returnValue(m)
                
    @setting(351, 'Sweep Power', p=['v[dBm]'], returns=['v[dBm]'])
    def sweep_power(self, c, p=None):
        dev = self.selectedDevice(c)
        if p is not None:
            yield dev.write('POWE %.2f DB' % p)
        p = yield dev.query('POWE?').addCallback(float)
        p = T.Value(p, 'dBm')
        returnValue(p)
    
    @setting(367, 'Num Points', np=['v'], returns=['v'])
    def num_points(self, c, np=None):
        dev = self.selectedDevice(c)
        if np is not None:
            yield dev.write('POIN %d' % np)
        np = yield dev.query('POIN?').addCallback(float).addCallback(int)
        returnValue(np)
        
    @setting(368, 'Cal Kit', ck=['s'], returns=['s'])
    def cal_kit(self, c, ck=None):
        dev = self.selectedDevice(c)
        cal_kits = ['CALK24MM', 'CALK292MM', 'CALK292S', 'CALK32F', 'CALK35MC', 'CALK35MD',
                    'CALK35ME', 'CALK716', 'CALK7MM', 'CALKN50', 'CALKN75', 'CALKTRLK', 'CALKUSED']
        if ck is not None:
            ck = ck.upper()
            if ck not in cal_kits:
                raise Exception("Invalid cal kit")
            yield dev.write(ck)
        for s in cal_kits:
            sbool = yield dev.query(s+'?').addCallback(int).addCallback(bool)
            if sbool:
                ck = s
        returnValue(ck)
    
    # Modify 3.5mmD calibration kit for CS-5 calibration board
    @setting(369, 'Set CS5 Cal', returns=['b'])
    def set_cs5_cal(self, c):
        dev = self.selectedDevice(c)
        yield self.cal_kit(c, 'CALK35MD') # Select cal kit to modify
        yield dev.write('MODI1')       # Begin 'modify cal kit' sequence
        
        yield dev.write('DEFS 1')       # Begin 'Define Standard 1' sequence (short)
        # OFS<D|L|Z><num> specify offset value for indicated parameter
        shortDelay = 0.257
        yield dev.write('OFSD %.3f ps' % shortDelay)
        yield dev.write('COAX')
        yield dev.write('STDD')        # Standard Done (Defined)
        
        yield dev.write('DEFS 2') # Begin 'Define Standard 2' sequence (open)
        C0 = 6.5 # pF
        yield dev.write('C0 %.3f' % C0)
        yield dev.write('C1 0')
        yield dev.write('C2 0')
        yield dev.write('C3 0')
        openDelay = 0.327
        yield dev.write('OFSD %.3f ps' % openDelay)
        yield dev.write('COAX')
        yield dev.write('STDD')
        
        yield dev.write('DEFS 3') # Begin 'Define Standard 3' sequence (load)   
        yield dev.write('COAX')
        yield dev.write('STDD')
        
        yield dev.write('DEFS 4') # Begin 'Define Standard 4' sequence (thru)
        thruDelay = 1.13
        yield dev.write('OFSD %.3f ps' % thruDelay)
        yield dev.write('COAX')
        yield dev.write('STDD')        # Standard Done (Defined)
        
        yield dev.write('LABK "CS5"')
        yield dev.write('KITD')        # Kit Done (Modified)
        yield dev.write('SAVEUSEK')
        yield dev.write('CALKUSED')
        
        returnValue(True)
        
    @setting(370, 'Run Calibration', returns=['b'])
    def run_calibration(self, c):
        dev = self.selectedDevice(c)
        time = yield dev.query('SWET?').addCallback(float)
        ck = yield self.cal_kit(c, 'CALKUSED')
        print 'Running full 2-port calibration with cal kit ' + ck
        yield dev.write('CALIFUL2')
        yield dev.write('REFL')
        print 'Connect open at Port 1. Press Enter to continue...'
        raw_input() 
        print 'Measuring...'
        sbool = yield dev.write('OPC?;CLASS11A')
        sleep(time) 
        yield dev.write('DONE')
        
        print 'Connect open at Port 2. Press Enter to continue...' 
        raw_input()
        print 'Measuring...'
        sbool = yield dev.write('OPC?;CLASS22A')
        sleep(time) 
        yield dev.write('DONE')
        
        print 'Connect short at Port 1. Press Enter to continue...'
        raw_input()
        print 'Measuring...'
        sbool = yield dev.write('OPC?;CLASS11B')
        sleep(time) 
        yield dev.write('DONE')
        
        print 'Connect short at Port 2. Press Enter to continue...'
        raw_input()
        print 'Measuring...'
        sbool = yield dev.write('OPC?;CLASS22B')
        sleep(time) 
        yield dev.write('DONE')
        
        print 'Connect load at Port 1. Press Enter to continue...'
        raw_input()
        print 'Measuring...'
        yield dev.write('CLASS11C')
        sbool = yield dev.write('OPC?;STANA')
        sleep(time) 
        yield dev.write('DONE')
                
        print 'Connect load at Port 2. Press Enter to continue...' 
        raw_input()
        print 'Measuring...'
        yield dev.write('CLASS22C')
        sbool = yield dev.write('OPC?;STANA')
        sleep(time) 
        yield dev.write('DONE')
        
        yield dev.write('REFD')
        yield dev.write('TRAN')
        
        print('Connect thru (Port 1 to Port 2). Press Enter to continue...')
        raw_input()
        print 'Measuring...'
                
        sbool = yield dev.write('OPC?;FWDT')
        sleep(time) # avoid timeout error
        sbool = yield dev.write('OPC?;FWDM')
        sleep(time) # avoid timeout error
        sbool = yield dev.write('OPC?;REVT')
        sleep(time) # avoid timeout error
        sbool = yield dev.write('OPC?;REVM')
        sleep(time) # avoid timeout error
        
        yield dev.write('TRAD')
        
        # Skip isolation (?)
        yield dev.write('OMII')
        
        sbool = yield dev.write('OPC?;SAV2')
        
        print 'Done with full 2-port cal. On VNA, press LOCAL hardkey, SAVE/RECALL hardkey, and save calibration state to a device register.'
        
        returnValue(sbool == 1)
        # ...        
     
    # # ... Get real and imaginary parts, assuming time domain by default
    # @setting(371, 'Get All Displays', measured=['b'], td=['b'])
    # def get_all_displays(self, c, measured=False, td=True):    
        # def parseData(data):
            # data = data.split('\n')
            # for i in range(len(data)):
                # stuff = data[i].split(',')
                # num1 = float(stuff[0])
                # num2 = float(stuff[1])
                # # num1 is real, num2 is imaginary
                # # units is U (dimensionless... Vout/Vin)
                # data[i] = [num1, num2]
            # return data1
        # dev = self.selectedDevice(c)
        # if not measured:
            # time = yield dev.query('SWET?').addCallback(float)        
            # yield dev.write('FORM4') # Set the output format 
            # yield dev.write('SING') # Perform a single sweep
            # sleep(2*time) # avoid timeout error
        # yield dev.write('SMIC')
        # result = yield dev.query('OUTPFORM') # Get the data
        # data = parseData(result)
        # data = array(data)
        # start_freq = yield self.start_frequency(c)
        # stop_freq = yield self.stop_frequency(c)
        # num_point = yield self.num_points(c)
        # freqs = linspace(start_freq, stop_freq, num_point)
        # data = hstack((transpose([freqs]),data))
        # returnValue(data)
__server__ = Agilent_8720ES_Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
