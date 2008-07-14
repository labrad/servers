#!c:\python25\python.exe

# Copyright (C) 2008  Max Hofheinz
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
from labrad.errors import Error
from labrad.server import LabradServer, setting

from twisted.python import log
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue
from time import sleep
from ctypes import windll, create_string_buffer, c_byte

class NoSuchDeviceError(Error):
    """No such Darlington board device"""
    code = 1
class NoDeviceSelectedError(Error):
    """No Darlington board device has been selected in this context."""
    code = 3

class NoSuchChannelError(Error):
    """This bitnumer does not exist on the selected Darlington board"""
    
class CSBBoardServer(LabradServer):
    name = '%LABRADNODE% Darlington Board'

    @inlineCallbacks
    def initServer(self):
        self.CSBBoards = []
        dll = yield windll.LoadLibrary('CSB14xxDll')
        self.dll = dll
        s = create_string_buffer(32)
        yield dll.GetDllVersion(s)
        print 'DLL revision: %s' % s.raw.split('\0x')[0]
        self.boards = []
        self.nChannels = []
        yield self.scanForBoards()

    @inlineCallbacks
    def scanForBoards(self):
        self.boards=[]
        self.nChannels={}
        nBoards = yield self.dll.GetNumberOfModules()
        print 'Searching for CSB boards:'
        for i in range(nBoards):
            serialN = create_string_buffer(32)
            yield self.dll.GetSerialNumber(i+1, serialN)
            serialN = serialN.value
            self.boards.append(serialN)
            nChannels = yield self.dll.GetNumberOfIO(serialN)
            self.nChannels[serialN] = nChannels
            print '%d: %s, %d bits'  % (i, serialN, nChannels)
        
        
        
    @setting(0, 'List Devices', returns=['*(ws): List of CSB boards'])
    def list_devices(self, c):
        yield self.scanForBoards()
        returnValue([(i,n) for i,n in enumerate(self.boards)])
    

    @setting(10, 'Select Device',
                 board=[': connect to first available board',
                        'w: connect to nth available board',
                       's: connect to board with serial no'],
                 returns=['s: selected board'])

    def select_device(self, c, board):
        if isinstance(board, (int,long)):
            if board >= len(self.boards):
                raise NoSuchDeviceError()
            c['board'] = self.boards[board]
        else:
            if not board in self.boards:
                raise NoSuchDeviceError()
            c['board'] = board
        return c['board']
            
        
    @setting(20, 'Set Bit',
                bit=['w: bit number'],
                value=['b: bit value'])
    def set_bit(self,c, bit, value):
        if 'board' not in c:
            raise NoDeviceSelectedError()
        if (bit < 1) or (bit > self.nChannels[c['board']]):
            raise NoSuchChannel()
        yield self.dll.SetDataBit(c['board'], c_byte(bit), value)


    @setting(30, 'sequence',
             seq=['*(wbv[s]): (bit number, value, duration)'])
    def sequence(self, c, seq):
        if 'board' not in c:
            raise NoDeviceSelectedError()
        # check if the sequence is valid before starting to execute it

        for bit, val, t in seq:
            t = t['s']
            if (bit < 1) or (bit > self.nChannels[c['board']]):                
                raise NoSuchChannel()
        for bit, val, t in seq:
            yield self.dll.SetDataBit(c['board'], c_byte(bit), val)
            yield sleep(t * (t>0))

__server__ = CSBBoardServer()
            
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
