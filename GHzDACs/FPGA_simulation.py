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

DAC_SRAM_LEN = 10240 #words
DAC_SRAM_PAGE_LEN = 256 #words
DAC_SRAM_PAGES = DAC_SRAM_LEN/DAC_SRAM_PAGE_LEN
DAC_SRAM_DTYPE = np.uint8

class FPGAWrapper(object):
    def __init__(self):
        pass

class DACWrapper(FPGAWrapper):
    """ Represents a GHzDAC board.
    ATTRIBUTES
    sram - numpy array representing the board's SRAM.
        each element is of type <u4, meaning little endian, four bytes.
    """
    def __init__(self):
        self.sram = np.zeros(DAC_SRAM_LEN, dtype=DAC_SRAM_DTYPE)
        self.register = np.zeros(DAC_REG_BYTES)

    def handle_packet(self, packet):
        """Handle an incoming ethernet packet to this board"""
        if len(packet) == DAC_SRAM_PACKET_LENGTH:
            self.handle_sram_packet(packet)
        elif len(packet) == REG_PACKET_LENGTH:
            self.handle_register_packet(packet)
        else:
            raise Exception('GHzDAC packet length not appropriate for register or SRAM')

    def handle_sram_packet(self, packet):
        """Stores SRAM data from a packet in the device's SRAM.

        PARAMETERS
        packet - numpy array of 

        SRAM packets have 256 words, each word is 32 bits long (4 bytes)
        One word represents 1 ns of sequence data.
        Each word has 14 bits for each DAC channel, plus four bits for the four ECL triggers (=32 bits).
        Each byte has the following form:
            bits[13..0] = DACA[13..0] D/A converter A
            bits[13..0] = DACB[13..0] D/A converter B
            bits[31..28]= SERIAL[3..0] ECL serial output
        """
        
        
class ADCWrapper(FPGAWrapper):
    pass
        
class FPGASimulationServer(LabradServer):

    @setting(10, 'adapters', returns='*(ws)')
    def adapters(self, c):
        """Retrieves a list of network adapters"""
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
        raise Exception

    @setting(14, 'Destination MAC', mac=['s: Destination MAC as 01:23:45:67:89:AB',
                                         '(wwwwww): MAC as individual numbers'],
             returns = 's')
    def destination_mac(self, c, mac):
        raise Exception

    @setting(15, 'Discard', num=[': Discard one packet',
                                 'w: Discard this many packets'],
             returns = '')
    def discard(self, c, num):
        raise Exception

    @setting(16, "Ether Type", returns='')
    def ether_type(self, c):
        raise Exception

    @setting(17, 'Listen', returns='')
    def listen(self,c):
        """Starts listening for SRAM packets"""
        raise Exception

    @setting(18, 'Read', num=[': Read one packet (returns (ssis))',
                              'w: Read this many packets (returns *(ssis))'],
             returns=['(ssis): Source MAC, Destination MAC, Ether Type (-1 for IEEE 802.3, and Data of received packet',
                      '*(ssis): List of above'])
    def read(self, c, num):
        raise Exception

    @setting(19, 'Read as Words', num=[': Read one packet (returns (ssi*w))',
                              'w: Read this many packets (returns *(ssi*w))'],
             returns=['(ssi*w): Source MAC, Destination MAC, Ether Type (-1 for IEEE 802.3, and Data of received packet',
                      '*(ssi*w): List of above'])
    def read_as_words(self, c, num):
        raise Exception


    @setting(20, 'Reject Content', pattern=['(ws): Offset,data',
                                            '(w*w): Offset, data'],
             returns='')
    def reject_content(self, c):
        """If the packet content matches, the packet will be rejected."""
        raise Exception
    
    @setting(21, 'Reject Destination MAC', mac=['s: MAC in string form: 01:23:45:67:89:AB',
                                                '(wwwwww): MAC as individual numbers'],
             returns='s')
    def reject_destination_mac(self, c, mac):
        raise Exception

    @setting(22, 'Require Source MAC', mac=['s: MAC in string form: 01:23:45:67:89:AB',
                                            '(wwwwww): MAC as individual numbers'],
             returns='s')
    def require_source_mac(self, c, mac):
        raise Exception

    @setting(23, 'Send Trigger', context='(w,w): Target context', returns='')
    def send_trigger(self, c, context):
        raise Exception

    @setting(24, 'Source MAC', mac=[': Use adapter MAC as default',
                                    's: Source MAC as 01:23:45:67:89:AB',
                                    'w: Source MAC as individual numbers'],
             returns='s')
    def source_mac(self, c, mac):
        raise Exception

    @setting(25, 'Wait For Trigger', num=[': Wait for one trigger', 'w: Wait for this number of triggers'],
             returns = 'v[s]: Elapsed wait time')
    def wait_for_trigger(self, c, num):
        raise Exception

    @setting(26, 'Write', data=['s: Send data as one packet', '*w: Same, except data is specified as an array of words'],
             returns='')
    def write(self, c, data):
        raise Exception
    
