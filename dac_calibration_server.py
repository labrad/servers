#!c:\python25\python.exe

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

from labrad import types as T, util
from labrad.server import LabradServer, setting
from ghzdac import IQcorrectorAsync, DACcorrectorAsync
from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from datetime import datetime


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
    """No DAC or frequency"""
    code = 4

class DACrequiresRealError(T.Error):
    """Only single-channel data can be corrected for a DAC"""
    code = 5


class CalibrationServer(LabradServer):
    name = 'DAC Calibration'

    def initServer(self):
        self.IQcalsets={}
        self.DACcalsets={}

    @setting(1, 'Board', board=['s'], returns=['s'])
    def board(self, c, board):
        """Sets the board for which to correct the data."""
        c['Board'] = board
        return board

    @setting(10, 'Frequency', frequency=['v[GHz]'], returns=['v[GHz]'])
    def frequency(self, c, frequency):
        """Sets the microwave driving frequency for which to correct the data.
        Selects I/Q mode for the correction."""
        c['Frequency'] = frequency.value
        c['DAC'] = None
        return frequency

    @setting(11, 'Loop', loopmode=['b: Loop mode'], returns=['b'])
    def loop(self, c, loopmode=True):
        c['Loop'] = loopmode
        return loopmode
    
    @setting(20, 'DAC', dac=['w: DAC channel 0 or 1', 's: DAC channel'], returns=['w'])
    def dac(self, c, dac):
        """Set the DAC for which to correct the data.
        Selects single channel mode for the correction."""
        if isinstance(dac, str):
            dac = dac[-1]
        if dac in [0,'0','a','A']:
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
        """Corrects data"""
        # All settings there?
        if 'Board' not in c:
            raise NoBoardSelectedError()
        
        if 'DAC' not in c:
            raise NoDACSelectedError()
        if 'Loop' not in c:
            c['Loop'] = False
        
        # No data?
        if len(data)==0:
            returnValue([])

        if c['DAC'] is None:
            # IQ mixer calibration
            if c['Board'] not in self.IQcalsets:
                self.IQcalsets[c['Board']]=\
                  yield IQcorrectorAsync(c['Board'], self.client,
                            errorClass = CalibrationNotFoundError)
            if isinstance(data[0], tuple):
                data = [re+im*1j for re,im in data]
            # convert data from *v to numpy array if desired
            corrected = self.IQcalsets[c['Board']].DACify(c['Frequency'], data, loop=c['Loop'], zipSRAM=False)
            # convert corrected to *v
            returnValue(corrected)
        else:
            # Single Channel Calibration
            if c['Board'] not in self.DACcalsets:
                self.DACcalsets[c['Board']] = {}
            if c['DAC'] not in self.DACcalsets[c['Board']]:
                self.DACcalsets[c['Board']][c['DAC']] = \
                    yield DACcorrectorAsync(c['Board'], c['DAC'], self.client,
                            errorClass = CalibrationNotFoundError)

            corrected = self.DACcalsets[c['Board']][c['DAC']].DACify(data,loop=c['Loop'], fitRange=False)
            returnValue(corrected)



__server__ = CalibrationServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
