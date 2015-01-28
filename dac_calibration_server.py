# Copyright (C) 2007  Markus Ansmann, Max Hofheinz 
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
name = DAC Calibration
version = 1.1.2
description = Calibrate sequences for the GHz DAC boards.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""


# CHANGELOG:
#
# 2012 April 12 - Jim Wenner
#
# See correction.py - changed logic string in setSettling.
#
#
# 2013 Dec R. Barends
# - loads values from registry
# - added support for setting the border values - necessary for dualblock
# - added support for disabling deconvolution on all IQ boards and/or all Z boards


from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.types import Error
from labrad.server import LabradServer, setting

from ghzdac import IQcorrectorAsync, DACcorrectorAsync, keys #,loadServerSettings
from ghzdac.correction import fastfftlen


class CalibrationNotFoundError(Error):
    code = 1
    def __init__(self, caltype):
        self.msg = "No " + caltype + " calibration available for this board."

class NoSuchDACError(Error):
    """No such DAC"""
    code = 2

class NoBoardSelectedError(Error):
    """No board selected"""
    code = 3

class NoDACSelectedError(Error):
    """No DAC or frequency selected"""
    code = 4

class DACrequiresRealError(Error):
    """Only single-channel data can be corrected for a DAC"""
    code = 5


class CalibrationServer(LabradServer):
    name = 'DAC Calibration'

    @inlineCallbacks
    def initServer(self):
        self.IQcalsets = {}
        self.DACcalsets = {}  
        print 'loading server settings...',
        yield self.loadServerSettings()
        print 'done.'
        yield LabradServer.initServer(self)

    @inlineCallbacks
    def loadServerSettings(self):
        """Load configuration information from the registry."""   
        reg = self.client.registry()
        yield reg.cd(['', 'Servers', 'DAC Calibration', keys.SERVERSETTINGS ], True)
        dict={}
        for key in keys.SERVERSETTINGVALUES:
            default=None
            if key == 'deconvIQ': default=True
            if key == 'deconvZ' : default=True
            if key == 'bandwidthIQ' : default=0.4 #original default: 0.4
            if key == 'bandwidthZ'  : default=0.13 #original default: 0.13
            if key == 'maxfreqZ' : default=0.45 #optimal parameter: 10% below Nyquist frequency of dac, 0.45
            if key == 'maxvalueZ' : default = 5.0 #optimal parameter: 5.0, from the jitter in 1/H fourier amplitudes
            if key == 'zeroIQ' : default=False
            if key == 'zeroZ': default=True              
            keyval = yield reg.get(key,False,default)
            if not isinstance(keyval,bool):
                #keyval is a number, in labrad units
                keyval=keyval
            print key,':', keyval
            dict[key]=keyval         
        self.serverSettings=dict
    
    #@inlineCallbacks        
    def initContext(self, c):
        c['Loop'] = False
        c['t0'] = 0
        c['Settling'] = ([],[])
        c['Filter'] = 0.2
        c['zeroIQ']=self.serverSettings['zeroIQ']
        c['zeroZ']=self.serverSettings['zeroZ']
        c['deconvIQ']=self.serverSettings['deconvIQ']
        c['deconvZ']=self.serverSettings['deconvZ']
        c['borderValues']=[0.0,0.0]

    @inlineCallbacks
    def getIQcalset(self, c):
        """Get an IQ calset for the board in the given context, creating it if needed."""
        if 'Board' not in c:
            raise NoBoardSelectedError()
        board = c['Board']
        
        if board not in self.IQcalsets:
            calset = yield IQcorrectorAsync(board, self.client,
                                            errorClass=CalibrationNotFoundError,bandwidth=self.serverSettings['bandwidthIQ'])
            self.IQcalsets[board] = calset
        returnValue(self.IQcalsets[board])
    
    @inlineCallbacks
    def getDACcalset(self, c):
        """Get a DAC calset for the board and DAC in the given context, creating it if needed."""
        if 'Board' not in c:
            raise NoBoardSelectedError()
        board = c['Board']
        
        if 'DAC' not in c:
            raise NoDACSelectedError()
        dac = c['DAC']
        
        if board not in self.DACcalsets:
            self.DACcalsets[board] = {}
        if dac not in self.DACcalsets[board]:
            calset = yield DACcorrectorAsync(board, dac, self.client,
                                             errorClass=CalibrationNotFoundError,bandwidth=self.serverSettings['bandwidthZ'],maxfreqZ=self.serverSettings['maxfreqZ'])
            self.DACcalsets[board][dac] = calset
        returnValue(self.DACcalsets[board][dac])

    @setting(1, 'Board', board=['s'], returns=['s'])
    def board(self, c, board):
        """Sets the board for which to correct the data."""
        c['Board'] = board
        return board

    @setting(2, 'borderValues', borderValues= ['*v'], returns=['*v'])
    def set_border_values(self,c,borderValues):
        """Sets the end value to be enforced on the deconvolved output. By default it is zero, for single block. For dual block this must be set"""
        c['borderValues']=borderValues
        return c['borderValues']
        
    @setting(10, 'Frequency', frequency=['v[GHz]'], returns=['v[GHz]'])
    def frequency(self, c, frequency):
        """Sets the microwave driving frequency for which to correct the data.
        
        This also implicitly selects I/Q mode for the correction.
        """
        # c['Frequency'] = float(frequency)
        c['Frequency'] = frequency['GHz']
        c['DAC'] = None
        return frequency

    @setting(11, 'Loop', loopmode=['b: Loop mode'], returns=['b'])
    def loop(self, c, loopmode=True):
        c['Loop'] = loopmode
        return loopmode
    
    @setting(12, 'Time Offset', t0=['v[ns]'], returns=['v[ns]'])
    def set_time_offset(self, c, t0):
        # c['t0'] = float(t0)
        c['t0'] = t0['ns']
        return t0
    
    @setting(13, 'deconvIQ', deconvIQ=['b'], returns=['b'])
    def set_deconvIQ(self, c, deconvIQ):
        c['deconvIQ'] = deconvIQ
        return deconvIQ    
    
    @setting(14, 'deconvZ', deconvZ=['b'], returns=['b'])
    def set_deconvZ(self, c, deconvZ):
        c['deconvZ'] = deconvZ
        return deconvZ

    @setting(15, 'getdeconvIQ', returns=['b'])
    def get_deconvIQ(self, c):
        return c['deconvIQ'] 
        
    @setting(16, 'getdeconvZ', returns=['b'])
    def get_deconvZ(self, c):
        return c['deconvZ']    
    
    @setting(20, 'DAC', dac=['w: DAC channel 0 or 1', 's: DAC channel'], returns=['w'])
    def dac(self, c, dac):
        """Set the DAC for which to correct the data.
        
        This also implicitly selects single channel mode for the correction.
        If a string is passed in, the final character is used to select the DAC,
        and must be either 'A' ('a') or 'B' ('b').
        """
        if isinstance(dac, str):
            dac = dac[-1]
        if dac in [0, '0', 'a', 'A']:
            dac = 0
        elif dac in [1, '1', 'b', 'B']:
            dac = 1
        else:
            raise NoSuchDACError()
     
        c['Frequency'] = None
        c['DAC'] = dac
        return dac

           
    @setting(30, 'Correct', data=['*v: Single channel data', '*(v, v): I/Q data', '*c: I/Q data'],
             returns=['*i: Single channel DAC values', '(*i, *i): Dual channel DAC values'])
    def correct(self, c, data):
        """Corrects data specified in the time domain."""
        # All settings there?
        if 'DAC' not in c:
            raise NoDACSelectedError()
        
        # data = data.asarray # convert data to array
        if len(data) == 0:
            returnValue([]) # special case for empty data

        if c['DAC'] is None:
            # IQ mixer calibration
            if len(data.shape) == 2:
                data = data[:,0] + 1j * data[:,1]
            calset = yield self.getIQcalset(c)
            deconv=c['deconvIQ']
            corrected = calset.DACify(c['Frequency'], data, loop=c['Loop'], zipSRAM=False,deconv=deconv,zeroBoards=c['zeroIQ'])
            if deconv is False:
                print 'No deconv on board ' + c['Board'] 
        else:
            # Single Channel Calibration
            calset = yield self.getDACcalset(c)
            deconv=c['deconvZ']
            corrected = calset.DACify(data, loop=c['Loop'], fitRange=False,deconv=deconv,borderValues=c['borderValues'],zeroBoards=c['zeroZ'])
            if deconv is False:
                print 'No deconv on board ' + c['Board']          
        returnValue(corrected)
    
    @setting(31, 'Correct FT', data=['*v: Single channel data', '*(v, v): I/Q data', '*c: I/Q data'],
             returns=['*i: Single channel DAC values', '(*i, *i): Dual channel DAC values'])
    def correct_ft(self, c, data):
        """Corrects data specified in the frequency domain.
        
        This allows for sub-nanosecond timing resolution.
        """
        # All settings there?
        if 'DAC' not in c:
            raise NoDACSelectedError()
        
        # data = data.asarray # convert data to array
        if len(data) == 0:
            returnValue([]) # special case for empty data

        if c['DAC'] is None:
            # IQ mixer calibration
            if len(data.shape) == 2:
                data = data[:,0] + 1.0j * data[:,1]
            calset = yield self.getIQcalset(c)
            deconv=c['deconvIQ']            
            corrected = calset.DACifyFT(c['Frequency'], data, n=len(data),
                                        t0=c['t0'], loop=c['Loop'], zipSRAM=False,
                                        deconv=deconv, zeroBoards=c['zeroIQ'])
            if deconv is False:
                print 'No deconv on board ' + c['Board']                                         
        else:
            # Single Channel Calibration
            calset = yield self.getDACcalset(c)
            calset.setSettling(*c['Settling'])
            calset.setFilter(bandwidth=c['Filter'])
            deconv=c['deconvZ']            
            corrected = calset.DACifyFT(data, n=(len(data)-1)*2,
                                        t0=c['t0'], loop=c['Loop'], fitRange=False,
                                        deconv=deconv, zeroBoards=c['zeroZ'], borderValues=c['borderValues'],
                                        maxvalueZ=self.serverSettings['maxvalueZ'])
            if deconv is False:
                print 'No deconv on board ' + c['Board']                                          
        returnValue(corrected)
    
    @setting(40, 'Set Settling', rates=['*v[GHz]: settling rates'], amplitudes=['*v: settling amplitudes'])
    def setsettling(self, c, rates, amplitudes):
        """
        If a calibration can be characterized by time constants, i.e.
        the step response function is
          0                                             for t <  0
          1 + sum(amplitudes[i]*exp(-decayrates[i]*t))  for t >= 0,
        then you don't need to load the response function explicitly
        but can just give the timeconstants and amplitudes.
        All previously used time constants will be replaced.
        """
        c['Settling'] = (rates, amplitudes)

    @setting(45, 'Set Filter', bandwidth=['v[GHz]: bandwidth'])
    def setfilter(self, c, bandwidth):
        """
        Set the lowpass filter used for deconvolution.
                       
        bandwidth: bandwidth are arguments passed to the lowpass
            filter function (see above)
        """
        c['Filter'] = float(bandwidth)

    @setting(50, 'Fast FFT Len', n='w')
    def fast_fft_len(self, c, n):
        """Given a sequence length n, get a new length nfft >= n which is efficient for calculating fft."""
        return fastfftlen(n)


         

      
__server__ = CalibrationServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)