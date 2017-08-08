import time
import os
from twisted.internet import defer

DUMP_NUM = 0
DEBUG_PATH = os.path.join(os.path.expanduser('~'), 'packet-dump')

TEMP = {
    'ether_type' : 62 ,
    'connect' : 10 ,
    'write' : 65 ,
    'require_source_mac' : 100 ,
    'require_length' : 120 ,
    'send_trigger' : 200 ,
    'reject_content' : 141 ,
    'wait_for_trigger' : 201 ,
    'reject_destination_mac' : 111 ,
    'destination_mac' : 61 ,
    'listen' : 20 ,
    'require_content' : 140 ,
    'read' : 50 ,
    'source_mac' : 60 ,
    'reject_ether_type' : 131 ,
    'require_destination_mac' : 110 ,
    'require_ether_type' : 130 ,
    'clear' : 55 ,
    'collect' : 40 ,
    'reject_length' : 121 ,
    'timeout' : 30 ,
    'read_as_words' : 51 ,
    'discard' : 52 ,
    'adapters' : 1 ,
    'reject_source_mac' : 101 ,
}

DIRECT_ETHERNET_SETTINGS = {}
for key,val in TEMP.items():
    DIRECT_ETHERNET_SETTINGS[val] = key

def littleEndian(data, bytes=4):
    return [(data >> ofs) & 0xFF for ofs in (0, 8, 16, 24)[:bytes]]


class TimedLock(object):
    """
    A lock that times how long it takes to acquire.
    """

    TIMES_TO_KEEP = 100
    locked = 0

    def __init__(self):
        self.waiting = []

    @property
    def times(self):
        if not hasattr(self, '_times'):
            self._times = []
        return self._times

    def addTime(self, dt):
        times = self.times
        times.append(dt)
        if len(times) > self.TIMES_TO_KEEP:
            times.pop(0)

    def meanTime(self):
        times = self.times
        if not len(times):
            return 0
        return sum(times) / len(times)

    def acquire(self):
        """Attempt to acquire the lock.

        @return: a Deferred which fires on lock acquisition.
        """
        d = defer.Deferred()
        if self.locked:
            t = time.time()
            self.waiting.append((d, t))
        else:
            self.locked = 1
            self.addTime(0)
            d.callback(0)
        return d

    def release(self):
        """Release the lock.

        Should be called by whomever did the acquire() when the shared
        resource is free.
        """
        assert self.locked, "Tried to release an unlocked lock"
        self.locked = 0
        if self.waiting:
            # someone is waiting to acquire lock
            self.locked = 1
            d, t = self.waiting.pop(0)
            dt = time.time() - t
            self.addTime(dt)
            d.callback(dt)


# class LoggingPacketWrapper(object):
    # def __init__(self, packet, outFile=None):
        # self._packet = packet
        # self.outFile = outFile
    
    # def __getattr__(self, name):
        # return getattr(self._packet, name)

    # def send(self):
        # if self.outFile:
            # #self.outFile.write(self._packet._packet.__repr__()+',')
            # self.outFile.write(self._packet[0][1])
            # self.outFile.flush()
            # return self._packet.send()
        # else:
            # return self._packet.send()


class LoggingPacket(object):
    def __init__(self, p, name=None):
        self._packet = p
        self._name = name
    def __getattr__(self, name):
        return getattr(self._packet, name)
        
    def __getitem__(self, key):
        return self._packet[key]
    def __setitem__(self, key, value):
        self._packet[key] = value
        
    def send(self):
        global DUMP_NUM
        packetType = '-'.join([DIRECT_ETHERNET_SETTINGS[x[0]] for x in self._packet._packet])[0:100]
        fname = os.path.join(DEBUG_PATH, 'dac_packet_%d_%s.txt' %(DUMP_NUM, packetType))
        with open(fname, 'wb') as f:
            dumpPacketWithHash(f, self._packet, self._name)
        DUMP_NUM += 1
        return self._packet.send()


def dumpPacketWithHash(file, p, name):
    if name:
        print "Dumping Packet: ", name
    #toWrite = ''.join([str(x[1]) for x in p._packet])
    print str(p)
    toWrite = repr(p)
    file.write(toWrite)
    import hashlib
    m = hashlib.md5()
    m.update(toWrite)
    hash = m.digest()
    file.write('\nMD5 Hash:\n')
    hash_str = ':'.join('%02X' % (ord(c),) for c in hash)
    file.write(hash_str)


def getPacketInfo(filename="packetLog.txt"):
    with open(filename) as f:
        data = f.readlines()[0]
        data = data.replace('][', '],[')
        return data
