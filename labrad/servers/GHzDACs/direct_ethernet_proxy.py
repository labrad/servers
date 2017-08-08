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

import random
import time

import numpy as np
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad.server import LabradServer, setting


class EthernetAdapter(object):
    """Proxy for an ethernet adapter."""
    def __init__(self, name, mac):
        self.name = name
        self.mac = mac
        self.listeners = []
    
    def send(self, pkt):
        """Send a packet on this adapter."""
        for listener in self.listeners:
            listener(pkt)
    
    def addListener(self, listener):
        """Add a listener to be called for each sent packet."""
        self.listeners.append(listener)

    def removeListener(self, listener):
        """Remove a listener from this adapter."""
        self.listeners.remove(listener)


class LossyEthernetAdapter(EthernetAdapter):
    """Proxy for a lossy ethernet adapter that can drop packets."""
    def __init__(self, name, mac, pLoss=0.01):
        EthernetAdapter.__init__(self, name, mac)
        self.pLoss = pLoss
    
    def send(self, pkt):
        """Send a packet on this adapter."""
        for listener in listeners:
            if random.random() < self.pLoss:
                continue # simulate dropped packet
            listener(pkt)


class EthernetListener(object):
    """Listens for packets on an adapter.
    
    Filters can be added which examine incoming packets and
    return a boolean result.  Only if all filters match will
    a given packet be passed on.
    """
    def __init__(self, packetFunc):
        self.packetFunc = packetFunc
        self.listening = False
        self.filters = []
    
    def __call__(self, packet):
        if self.listening and all(filter(packet) for filter in self.filters):
            self.packetFunc(packet)
    
    def addFilter(self, filter):
        self.filters.append(filter)


class DeferredBuffer(object):
    """Buffer for packets/triggers received in a given context."""
    def __init__(self):
        self.buf = []
        self.waiter = None
        self.waitCount = 0
    
    def put(self, packet):
        self.buf.append(packet)
        if self.waiter and len(self.buf) >= self.waitCount:
            d = self.waiter
            self.waiter = None
            d.callback(None)
    
    def collect(self, n=1, timeout=None):
        assert (self.waiter is None), 'already waiting'
        if len(self.buf) >= n:
            return defer.succeed()
        else:
            d = defer.Deferred()
            if timeout is not None:
                timeoutCall = reactor.callLater(timeout, d.errback, Exception('timeout'))
                d.addCallback(self._cancelTimeout, timeoutCall)
            self.waiter = d
            self.waitCount = n
            return d

    def _cancelTimeout(self, result, timeoutCall):
        if timeoutCall.active():
            timeoutCall.cancel()
        return result
    
    def get(self, n=1, timeout=None):
        def _get(result):
            pkts = self.buf[:n]
            self.buf = self.buf[n:]
            return pkts
        d = self.collect(n)
        d.addCallback(_get)
        return d
    
    def discard(self, n=1, timeout=None):
        def _discard(result):
            self.buf = self.buf[n:]
        d = self.collect(n)
        d.addCallback(_discard)
        return d
    
    def clear(self):
        self.buf = []


def parseMac(mac):
    """Convert a string or tuple of words into a valid mac address."""
    if isinstance(mac, str):
        mac = tuple(int(s, 16) for s in mac.split(':'))
    return '%02X:%02X:%02X:%02X:%02X:%02X' % mac


class DirectEthernetProxy(LabradServer):
    name = 'Direct Ethernet Proxy'
    
    def __init__(self, adapters=[]):
        LabradServer.__init__(self)
        
        # make a dictionary of adapters, indexable by id or name
        d = {}
        for i, adapter in enumerate(adapters):
            d[i] = d[adapter.name] = adapter
        self.adapters = d
        
    def initServer(self):
        pass

    def initContext(self, c):
        c['triggers'] = DeferredBuffer()
        c['buf'] = DeferredBuffer()
        c['timeout'] = None
        c['listener'] = EthernetListener(c['buf'].put)
        c['listening'] = False
        c['src'] = None
        c['dest'] = None
        c['typ'] = -1

    def expireContext(self, c):
        if c['listening']:
            c['adapter'].removeListener(c['listener'])

    def getAdapter(self, c):
        """Get the selected adapter in this context."""
        try:
            return c['adapter']
        except KeyError:
            raise Exception('Need to connect to an adapter')
    
    
    # adapters
    
    @setting(1, 'Adapters', returns='*(ws)')
    def adapters(self, c):
        """Retrieves a list of network adapters"""
        adapterList = sorted((id, a.name) for id, a in self.adapters)
        return adapterList

    @setting(2, 'Connect', key=['s', 'w'], returns='s')
    def connect(self, c, key):
        try:
            adapter = self.adapters[key]
        except KeyError:
            raise Exception('Adapter not found: %s' % key)
        if 'adapter' in c:
            c['adapter'].removeListener(listener)
        adapter.addListener(c['listener'])
        c['adapter'] = adapter
        return adapter.name

    @setting(3, 'Listen', returns='')
    def listen(self, c):
        """Starts listening for SRAM packets"""
        c['listener'].listening = True


    # packet control and buffering

    @setting(10, 'Timeout', t='v[s]', returns='')
    def timeout(self, c, t):
        c['timeout'] = float(t)

    @setting(11, 'Collect', num='w', returns='')
    def collect(self, c, num=1):
        yield c['buf'].collect(num, timeout=c['timeout'])

    @setting(12, 'Discard', num=['w'], returns='')
    def discard(self, c, num=1):
        yield c['buf'].discard(num, timeout=c['timeout'])

    @setting(13, 'Read', num=['w'], returns=['(ssis)', '*(ssis)'])
    def read(self, c, num=1):
        def toStr(pkt):
            src, dest, typ, data = pkt
            data = np.tostring(data)
            return (src, dest, typ, data)
        return self._read(c, num, toStr)

    @setting(14, 'Read as Words', num=['w'], returns=['(ssi*w)', '*(ssi*w)'])
    def read_as_words(self, c, num):
        def toWords(pkt):
            src, dest, typ, data = pkt
            data = np.fromstring(data, dtype='uint8').astype('uint32')
            return (src, dest, typ, data)
        return self._read(c, num, toWords)

    @inlineCallbacks
    def _read(self, c, num, func=None):
        pkts = yield c['buf'].read(num, timeout=c['timeout'])
        if func is None:
            pkts = [func(pkt) for pkt in pkts]
        if num == 1:
            returnValue(pkts[0])
        else:
            returnValue(pkts)

    @setting(15, 'Clear', returns='')
    def clear(self, c):
        c['buf'].clear()
    

    # writing packets

    @setting(20, 'Source MAC', mac=['s', 'wwwwww'], returns='s')
    def source_mac(self, c, mac=None):
        if mac is not None:
            mac = parseMac(mac)
        c['src'] = mac
        return mac

    @setting(21, 'Destination MAC', mac=['s', 'wwwwww'], returns='s')
    def destination_mac(self, c, mac=None):
        if mac is not None:
            mac = parseMac(mac)
        c['dest'] = mac
        return mac

    @setting(22, "Ether Type", typ='i', returns='')
    def ether_type(self, c, typ):
        c['typ'] = typ

    @setting(23, 'Write', data=['s', '*w'], returns='')
    def write(self, c, data):
        adapter = self.getAdapter(c)
        src, dest, typ = c['src'], c['dest'], c['typ']
        if src is None:
            src = adapter.mac
        if dest is None:
            raise Exception('no destination mac specified!')
        if isinstance(data, str):
            data = np.fromstring(data, dtype='uint8')
        else:
            data = data.asarray.astype('uint8')
        pkt = (src, dest, typ, data)
        adapter.send(pkt)
        

    # packet filters
    
    @setting(100, 'Require Source MAC', mac=['s', 'wwwwww'], returns='s')
    def require_source_mac(self, c, mac):
        mac = parseMac(mac)
        c['listener'].addFilter(lambda pkt: pkt[0] == mac)
        return mac
    
    @setting(101, 'Reject Source MAC', mac=['s', 'wwwwww'], returns='s')
    def reject_source_mac(self, c, mac):
        mac = parseMac(mac)
        c['listener'].addFilter(lambda pkt: pkt[0] != mac)
        return mac
    
    @setting(110, 'Require Destination MAC', mac=['s', 'wwwwww'], returns='s')
    def require_destination_mac(self, c, mac):
        mac = parseMac(mac)
        c['listener'].addFilter(lambda pkt: pkt[1] == mac)
        return mac
    
    @setting(111, 'Reject Destination MAC', mac=['s', 'wwwwww'], returns='s')
    def reject_destination_mac(self, c, mac):
        mac = parseMac(mac)
        c['listener'].addFilter(lambda pkt: pkt[1] != mac)
        return mac

    @setting(120, 'Require Length', length='w', returns='')
    def require_length(self, c, length):
        c['listener'].addFilter(lambda pkt: len(pkt[3]) == length)
        
    @setting(121, 'Reject Length', length='w', returns='')
    def reject_length(self, c, length):
        c['listener'].addFilter(lambda pkt: len(pkt[3]) != length)

    @setting(130, 'Require Ether Type', typ='i', returns='')
    def require_ether_type(self, c, typ):
        c['listener'].addFilter(lambda pkt: pkt[2] == typ)
        
    @setting(131, 'Reject Ether Type', typ='i', returns='')
    def reject_ether_type(self, c, typ):
        c['listener'].addFilter(lambda pkt: pkt[2] != typ)
    
    @setting(140, 'Require Content', offset='w', data=['s', '*w'], returns='')
    def require_content(self, c, offset, data):
        raise Exception('not implemented')
    
    @setting(141, 'Reject Content', offset='w', data=['s', '*w'], returns='')
    def reject_content(self, c, offset, data):
        raise Exception('not implemented')


    # triggers

    @setting(200, 'Send Trigger', context='ww', returns='')
    def send_trigger(self, c, context):
        # have to send this to another context
        # this next line is a bit of a hack that depends on internal labrad details
        # should probably use an external bus object, like the ethernet adapter itself
        other = self.contexts[context].data['triggers'].put('trigger from %s' % c.ID)

    @setting(201, 'Wait For Trigger', num='w', returns='v[s]: Elapsed wait time')
    def wait_for_trigger(self, c, num=1):
        start = time.time()
        yield c['triggers'].discard(num) # does the real direct ethernet server have timeouts here?
        end = time.time()
        returnValue(end - start)

    

if __name__ == '__main__':
    from labrad import util
    import adc
    import dac
    
    # create ethernet
    adapter0 = EthernetAdapter('proxy0', '01:23:45:67:89:00')
    adapter1 = EthernetAdapter('proxy1', '01:23:45:67:89:01')
    
    # create devices
    dev00 = dac.DACProxy(0, adapter0)
    dev01 = dac.ADCProxy(1, adapter0)
    dev02 = dac.DACProxy(2, adapter0)
    
    dev10 = dac.DACProxy(0, adapter1)
    dev11 = dac.DACProxy(1, adapter1)
    dev12 = dac.ADCProxy(2, adapter1)
    
    server = DirectEthernetProxy([adapter0, adapter1])
    util.runServer(server)
