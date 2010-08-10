import numpy as np

def adcMAC(board):
    """Get the MAC address of an ADC board as a string."""
    return '00:01:CA:AA:01:' + ('0'+hex(int(board))[2:])[-2:].upper()

class ADCProxy(object):
    def __init__(self, id, adapter):
        self.id = id
        self.mac = adcMAC(id)
        self.adapter = adapter
        adapter.addListener(self)
    
    def __call__(self, packet):
        src, dest, typ, data = packet
        if dest != self.mac:
            return
        # process the packet
