"""
ethernet_spoofer.py

set of functions for listening and replying to ethernet packets, by MAC
address.

usage: 

spoofer = EthernetSpoofer('11:22:33:44:55:66')
packet = None
while packet is None:
    packet = spoofer.getPacket()
print "From %s: %s" % (packet['src'], packet['data'])

"""

import winpcapy as wp

class EthernetSpoofer(object):
    def __init__(self, address, device=0):
        '''
        Create a new spoofer.
        
        required: MAC address, in form 11:22:33:44:55:66
        optional: device number (i.e. NIC index), default=0
        '''
        self.adhandle = self.openDevice(device)
        self.setAddress(address)
        
    def openDevice(self, device):
        '''Open our ethernet device for listening'''
        # set up variables
        alldevs = wp.POINTER(wp.pcap_if_t)()
        errbuf = wp.create_string_buffer(wp.PCAP_ERRBUF_SIZE)
        # get all devices
        if (wp.pcap_findalldevs(wp.byref(alldevs), errbuf) == -1):
            raise RuntimeError("Error in pcap_findalldevs: %s\n" \
                               % errbuf.value)
        # find our device
        d = alldevs
        # d is a linked list, but not wrapped as a python list. Therefore, to
        # get element number device we can't do d[device]. Instead we just do
        # .next as many times as need to arrive at the device^th element.
        # These elements are all pointers, so to finally get the actual object
        # we call d.contents.
        for i in range(device):
            d = d.contents.next
        d = d.contents
        # open our device
        adhandle = wp.pcap_open_live(d.name, 65536,
                                     wp.PCAP_OPENFLAG_PROMISCUOUS, 1000,
                                     errbuf)
        wp.pcap_freealldevs(alldevs)
        if (adhandle == None):
            raise RuntimeError("Unable to open adapter %s" % d.contents.name)
        return adhandle
        
    def setFilter(self):
        ''' set the mac address filter. '''
        program = wp.bpf_program()
        filter = "ether dst %s" % self.mac
        # no idea what optimize should be, couldn't find doc, saw 1 in example code
        # netmask: 0xffffff ??
        if wp.pcap_compile(self.adhandle, wp.byref(program), filter, 1, 0xffffff) < 0:
            raise RuntimeError("Failed to compile filter: %s" % filter)
        if wp.pcap_setfilter(self.adhandle, wp.byref(program)) < 0:
            raise RuntimeError("Failed to set filter: %s" % filter)
        wp.pcap_freecode(wp.byref(program))
        
    def setAddress(self, address):
        ''' change the MAC address '''
        self.mac = address
        self.setFilter()
        
    def getPacket(self, returnErrors=False):
        ''' returns the data from the next packet, or None, if no packet is received.
        if returnErrors, then return -1 for error (or -2 if EOF reached, should never
        happen)
        data is returned as dict:
        { "dest"   : "11:22:33:44:55:66",
          "src"    : "aa:bb:cc:dd:ee:ff",
          "length" : 12,
          "data"   : "hello there!"
        }
        '''
        header = wp.POINTER(wp.pcap_pkthdr)()
        data = wp.POINTER(wp.c_ubyte)()
        r = wp.pcap_next_ex(self.adhandle, wp.byref(header), wp.byref(data))
        if r == 1:
            # process this packet
            pystr = wp.string_at(data, header.contents.len)
            # parse the header
            dest = self._macToString(pystr[0:6])
            src = self._macToString(pystr[6:12])
            length = ord(pystr[12])*256 + ord(pystr[13])
            return { "dest": dest, "src": src, "length": length, "data": pystr[14:] }
        elif r == 0:
            return None
        else:
            return r if returnErrors else None
            
    def sendPacket(self, destMac, data):
        ''' send a packet to destMat with given data.
        source mac is self.mac.
        returns 0 for success, otherwise returns error'''
        packet = self._macToData(destMac)   # bytes 0-5: destination address
        packet += self._macToData()         # 6-11: source address
        packet += chr(len(data) / 256)      # 12, 13 are packet length (big endian?)
        packet += chr(len(data) % 256)
        packet += data
        packet_c = (wp.c_ubyte*len(packet))()
        for i in range(len(packet)):
            packet_c[i] = ord(packet[i])
        if wp.pcap_sendpacket(self.adhandle, packet_c, len(packet)) != 0:
            return wp.pcap_geterr(self.adhandle)
        else:
            return 0

    def _macToData(self, mac=None):
        ''' Take a MAC address in form "11:22:33:44:55:66"
        and read each byte as hex numbers, return as 6-byte string.
        if mac=None, use self.mac '''
        if mac is None:
            mac = self.mac
        bytes = ''.join([chr(int(x, 16)) for x in mac.split(':')])
        if len(bytes) != 6:
            raise ValueError("MAC address is not 6 bytes: %s" % mac)
        return bytes
        
    def _macToString(self, bytes):
        ''' inverse of _macToData: take a 6-byte string (of numbers)
        and return string of form "11:22:33:44:55:66. '''
        if len(bytes) != 6:
            raise ValueError("MAC address is not 6 bytes: %s" % bytes)
        return ':'.join(['%02X' % ord(x) for x in bytes])
        
    def __del__ (self):
        ''' closes the device handle. __del__ is a bit untrustworthy,
        should probably come up with a better way to do this. '''
        wp.pcap_close(self.adhandle)