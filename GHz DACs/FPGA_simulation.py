# Copyright (C) 2007  Daniel Sank
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
name = FPGA Simulation
version = 1.0.0
description = Simulate ethernet communication with FPGA boards

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.types import Error
from labrad.server import LabradServer, setting

import numpy as np

class FPGAWrapper(object):
    def __init__(self):
        pass

class DACWrapper(FPGAWrapper):
    def __init__(self):
        self.sram = np.

class ADCWrapper(FPGAWrapper):
    pass
        
class FPGASimulationServer(LabradServer):

    @setting(10, 'adapters', returns='*(ws)')
    """Retrieves a list of network adapters"""
    def adapters(self, c):
        adapterList = [(0, 'nothing'),(1, 'here')]
        return adapterList

    @setting(11, 'clear', returns='')
    def clear(self, c):
        #Clear all pending packets out of the buffer.
        #Are the packets to write or packets to read?
        pass

    @setting(12, 'collect', num = '*i', returns = '')
    def collect(self, c, num):
        if num is None:
            #User did not specify number to collect. Wait for one packet
            num = 1
        return num

    @setting(13, 'connect', key=['s: Select device by name',
                                 'w: Select device by ID'],
             returns = 's: Adapter name')
    def connect(self, c, key):
        pass

    @setting(14, 'Destination MAC', mac=['s: Destination MAC as 01:23:45:67:89:AB',
                                         '(wwwwww): MAC as individual numbers'],
             returns = 's')
    def destination_mac(self, c, mac):
        pass

    @setting(15, 'Discard', num=[': Discard one packet',
                                 'w: Discard this many packets'],
             returns = '')
    def discard(self, c, num):
        pass

    @setting(16, "Ether Type", returns='')
    def ether_type(self, c):
        pass

    @setting(17, 'Listen', returns='')
    def listen(self,c):
        """Starts listening for SRAM packets"""
        pass

    @setting(18, 'Read', num=[': Read one packet (returns (ssis))',
                              'w: Read this many packets (returns *(ssis))'],
             returns=['(ssis): Source MAC, Destination MAC, Ether Type (-1 for IEEE 802.3, and Data of received packet',
                      '*(ssis): List of above'])
    def read(self,c num):
        pass

    @setting(19, 'Read as Words', num=[': Read one packet (returns (ssi*w))',
                              'w: Read this many packets (returns *(ssi*w))'],
             returns=['(ssi*w): Source MAC, Destination MAC, Ether Type (-1 for IEEE 802.3, and Data of received packet',
                      '*(ssi*w): List of above'])
    def read_as_words(self,c num):
        pass


    @setting(20, 'Reject Content', pattern=['(ws): Offset,data',
                                            '(w*w): Offset, data'],
             returns='')
    def reject_content(self,c ):
        """If the packet content matches, the packet will be rejected."""
        pass
    
    @setting(21, 'Reject Destination MAC', mac=['s: MAC in string form: 01:23:45:67:89:AB',
                                                '(wwwwww): MAC as individual numbers'],
             returns='s')
    def reject_destination_mac(self,c mac):
        pass

    @setting(22, 'Require Source MAC', mac=['s: MAC in string form: 01:23:45:67:89:AB',
                                            '(wwwwww): MAC as individual numbers'],
             returns='s')
    def require_source_mac(self, c, mac):
        pass

    @setting(23, 'Send Trigger', context='(w,w): Target context', returns='')
    def send_trigger(self, c, context):
        pass

    @setting(24, 'Source MAC', mac=[': Use adapter MAC as default',
                                    's: Source MAC as 01:23:45:67:89:AB',
                                    'w: Source MAC as individual numbers'],
             returns='s')
    def source_mac(self, c, mac):
        pass

    @setting(25, 'Wait For Trigger', num=[': Wait for one trigger', 'w: Wait for this number of triggers'],
             returns = 'v[s]: Elapsed wait time')
    def wait_for_trigger(self, c, num):
        pass

    @setting(26, 'Write', data=['s: Send data as one packet', '*w: Same, except data is specified as an array of words'],
             returns='')
    def write(self, c, data):
        pass
    
