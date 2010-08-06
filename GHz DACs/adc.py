class ADCProxy(object):
    def __init__(self, mac, adapter):
        self.mac = mac
        self.adapter = adapter
        adapter.addListener(self)
    
    def __call__(self, packet):
        src, dest, typ, data = packet
        if dest != self.mac:
            return
        # process the packet
