from twisted.internet import defer


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

