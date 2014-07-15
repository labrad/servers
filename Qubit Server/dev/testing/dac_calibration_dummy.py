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
version = 1.1.0
description = Calibrate sequences for the GHz DAC boards.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad import types as T
from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks, returnValue

from numpy import fft

class CalibrationNotFoundError(T.Error):
    code = 1
    def __init__(self, caltype):
        self.msg = "No " + caltype + " calibration available for this board."

class NoSuchDACError(T.Error):
    """No such DAC"""
    code = 2

class NoBoardSelectedError(T.Error):
    """No board selected"""
    code = 3

class NoDACSelectedError(T.Error):
    """No DAC or frequency selected"""
    code = 4

class DACrequiresRealError(T.Error):
    """Only single-channel data can be corrected for a DAC"""
    code = 5


class CalibrationServer(LabradServer):
    name = 'DAC Calibration'

    def initServer(self):
        self.IQcalsets = {}
        self.DACcalsets = {}

    def initContext(self, c):
        c['Loop'] = False
        c['t0'] = 0
        c['Settling'] = ([],[])
        c['Filter'] = 0.200

    @inlineCallbacks
    def getIQcalset(self, c):
        """Get an IQ calset for the board in the given context, creating it if needed."""
        if 'Board' not in c:
            raise NoBoardSelectedError()
        board = c['Board']
        
        if board not in self.IQcalsets:
            calset = yield IQcorrectorAsync(board, self.client,
                                            errorClass=CalibrationNotFoundError)
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
                                             errorClass=CalibrationNotFoundError)
            self.DACcalsets[board][dac] = calset
        returnValue(self.DACcalsets[board][dac])

    @setting(1, 'Board', board='s', returns='s')
    def board(self, c, board):
        """Sets the board for which to correct the data."""
        c['Board'] = board
        return board

    @setting(10, 'Frequency', frequency='v[GHz]', returns='')
    def frequency(self, c, frequency):
        """Sets the microwave driving frequency for which to correct the data.
        
        This also implicitly selects I/Q mode for the correction.
        """
        c['Frequency'] = frequency.value
        c['DAC'] = None

    @setting(11, 'Loop', loopmode='b: Loop mode', returns='')
    def loop(self, c, loopmode=True):
        c['Loop'] = loopmode
    
    @setting(12, 'Time Offset', t0='v[ns]', returns='')
    def set_time_offset(self, c, t0):
        c['t0'] = float(t0)
    
    @setting(20, 'DAC', dac=['w: DAC channel 0 or 1', 's: DAC channel'], returns='w')
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
        
        data = data.asarray # convert data to array
        if len(data) == 0:
            return []
            #returnValue([]) # special case for empty data

        if c['DAC'] is None:
            # IQ mixer calibration
            if len(data.shape) == 2:
                data = data[:,0] + 1j * data[:,1]
            #calset = yield self.getIQcalset(c)
            #corrected = calset.DACify(c['Frequency'], data, loop=c['Loop'], zipSRAM=False)
            print 'IQ deconvolution:', c['Board'], 'f:', c['Frequency']
            corrected = (data.real*0x1FFF).astype(int), (data.imag*0x1FFF).astype(int)
        else:
            # Single Channel Calibration
            #calset = yield self.getDACcalset(c)
            #corrected = calset.DACify(data, loop=c['Loop'], fitRange=False)
            print 'Analog deconvolution:', c['Board'], 'dac:', c['DAC']
            corrected = (data*0x1FFF).astype(int)
        return corrected
        #returnValue(corrected)
    
    @setting(31, 'Correct FT', data=['*v: Single channel data', '*(v, v): I/Q data', '*c: I/Q data'],
             returns=['*i: Single channel DAC values', '(*i, *i): Dual channel DAC values'])
    def correct_ft(self, c, data):
        """Corrects data specified in the frequency domain.
        
        This allows for sub-nanosecond timing resolution.
        """
        # All settings there?
        if 'DAC' not in c:
            raise NoDACSelectedError()
        
        data = data.asarray # convert data to array
        if len(data) == 0:
            return []
            #returnValue([]) # special case for empty data

        if c['DAC'] is None:
            # IQ mixer calibration
            if len(data.shape) == 2:
                data = data[:,0] + 1.0j * data[:,1]
            #calset = yield self.getIQcalset(c)
            #corrected = calset.DACifyFT(c['Frequency'], data, n=len(data),
            #                            t0=c['t0'], loop=c['Loop'], zipSRAM=False)
            print 'IQ deconvolution FT:', c['Board'], 'f:', c['Frequency'], 't0:', c['t0']
            data = fft.ifft(data)
            corrected = (data.real*0x1FFF).astype(int), (data.imag*0x1FFF).astype(int)
        else:
            # Single Channel Calibration
            #calset = yield self.getDACcalset(c)
            #calset.setSettling(*c['Settling'])
            #calset.setFilter(bandwidth=c['Filter'])
            #corrected = calset.DACifyFT(data, n=len(data),
            #                            t0=c['t0'], loop=c['Loop'], fitRange=False)
            print 'Analog deconvolution FT:', c['Board'], 'dac:', c['DAC'], 't0:', c['t0']
            data = fft.irfft(data)
            corrected = numpy.hstack(((data.real*0x1FFF).astype(int),
                                      (data.imag*0x1FFF).astype(int)))
        return corrected
        #returnValue(corrected)
    
    @setting(40, 'Set Settling', rates='*v[GHz]: settling rates', amplitudes='*v: settling amplitudes', returns='')
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
        c['Settling'] = (rates.asarray, amplitudes.asarray)

    @setting(45, 'Set Filter', bandwidth='v[GHz]: bandwidth', returns='')
    def setfilter(self, c, bandwidth):
        """
        Set the lowpass filter used for deconvolution.
                       
        bandwidth: bandwidth are arguments passed to the lowpass
            filter function (see above)
        """
        c['Filter'] = float(bandwidth)

    @setting(50, 'Fast FFT Len', n='w', returns='w')
    def fast_fft_len(self, c, n):
        """Given a sequence length n, get a new length nfft >= n which is efficient for calculating fft."""
        return fastfftlen(n)

__server__ = CalibrationServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
