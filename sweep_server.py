#!c:\python25\python.exe

# Copyright (C) 2008  Markus Ansmann
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

from labrad        import util, types as T
from labrad.server import LabradServer, setting
from labrad.units  import us, mV, Unit

from twisted.python         import log
from twisted.internet       import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from math import floor
from collections import defaultdict

PIPELINE_DEPTH = 8

class ContextBusyError(T.Error):
    """The context is currently busy"""
    code = 1

def rangeND(limits):
    """Return an N-D iterator over a set of limits."""
    if len(limits):
        cur = [0] * len(limits)
        while cur[0] < limits[0]:
            yield [c for c in cur]
            a = len(limits) - 1
            cur[a] += 1
            while (a > 0) and (cur[a] == limits[a]):
                cur[a] = 0
                a -= 1
                cur[a] += 1

def countND(limits):
    """Return the count of points in an N-D iterator over limits."""
    if len(limits):
        c = 1
        for l in limits:
            c *= l
        return c
    else:
        return 0

def sweepND(starts, steps, counts, pars):
    """Return an N-D iterator where each axis goes from start up by step."""
    for cur in rangeND(counts):
        pos = [start+step*count for start,step,count in zip(starts,steps,cur)]
        yield zip(pos, pars)

class SweepServer(LabradServer):
    """Allows the user to run sweeps by calling a server setting repeatedly
    while changing the values of parameters stored in the Registry.  The
    server implements pipelining, making each call in a separate context
    with the appropriate registry context being duplicated and then using
    registry overrides to update keys for the sweep itself.
    """
    name = 'Sweep Server'
    sendTracebacks = False

    def initServer(self):
        self.contextPool = []

    def initContext(self, c):
        # report message listeners
        c['Progress'] = []
        c['Completion'] = []
        c['Errors'] = []

    @inlineCallbacks
    def runPoint(self, c, regpkt, setting, semaphore, sweepvars):
        """Run a single point in a sweep."""
        try:
            if len(self.contextPool):
                ctxt = self.contextPool.pop()
            else:
                ctxt = self.client.context()
            try:
                yield regpkt.send(context=ctxt)
                result = yield setting(c.ID, context=ctxt)
            finally:
                self.contextPool.append(ctxt)
                semaphore.release()
            c['Pos'] += 1
            for tgt, msg in c['Progress']:
                self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, long(c['Pos']))])
            # TODO: use numpy arrays here if possible
            # TODO: make data vault saving optional
            result = result.aslist
            if len(result) > 0:
                if isinstance(result[0], list):
                    result = [sweepvars+res for res in result]
                else:
                    result = sweepvars+result
                yield self.client.data_vault.add(result, context=c.ID)
        except Exception, e:
            if 'Exception' not in c:
                c['Exception'] = e
                for tgt, msg in c['Errors']:
                    self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, str(e))]) 

    @inlineCallbacks
    def runSweep(self, c, sweeper, setting):
        """Run a sweep."""
        semaphore = defer.DeferredSemaphore(PIPELINE_DEPTH)
        for sweep in sweeper:
            if ('Abort' in c) or ('Exception' in c):
                break
            yield semaphore.acquire()
            p = self.client.registry.packet()
            p.duplicate_context(c.ID)
            for var in sweep:
                for reg in var[1]:
                    if len(reg[0]):
                        p.cd      (reg[0])
                        p.override(reg[1], var[0])
                        p.cd      (len(reg[0]))
                    else:
                        p.override(reg[1], var[0])
            self.runPoint(c, p, setting, semaphore, [v[0] for v in sweep])
        # make sure the sweep is done by acquiring every stage
        for a in range(PIPELINE_DEPTH):
            yield semaphore.acquire()
        for a in range(PIPELINE_DEPTH):
            semaphore.release()
        if 'Abort' in c:
            c['Abort'].callback(None)
            del c['Abort']
        if 'Busy' in c:
            if 'Exception' in c:
                c['Busy'].errback(c['Exception'])
            else:
                c['Busy'].callback(None)
            del c['Busy']
        # send completion notices
        b = ('Abort' not in c) and ('Exception' not in c)
        for tgt, msg in c['Completion']:
            self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, b)]) 
        

    @setting(1, 'Repeat', server=['s'], setting=['s'], count=['w'])
    def repeat(self, c, server, setting, count):
        """Call a server setting repeatedly."""
        if 'Busy' in c:
            raise ContextBusyError()
        c['Busy'] = defer.Deferred()
        if 'Exception' in c:
            del c['Exception']
        c['Pos'] = 0
        yield self.client.refresh()
        self.runSweep(c, NDsweeper([[1,count,1]]), self.client[server].settings[setting])
        print 'done'
        

    @setting(10, 'Simple Sweep', server=['s'], setting=['s'],
                                 sweeprangesandkeys=['*((vvvs)*(*ss))'],
                                 returns=['w'])
    def simple_sweep(self, c, server, setting, sweeprangesandkeys):
        """Run a simple sweep.

        The specified setting on the specified server will be called for
        each point in the sweep.  
        """
        if 'Busy' in c:
            raise ContextBusyError()
        if len(sweeprangesandkeys):
            c['Busy'] = defer.Deferred()
            if 'Exception' in c:
                del c['Exception']
            starts = []
            steps  = []
            counts = []
            others = []
            for rng, keys in sweeprangesandkeys:
                starts.append(float(rng[0])*Unit(rng[3]))
                d = rng[1]-rng[0]
                if d < 0:
                    s = -abs(rng[2])
                else:
                    s = abs(rng[2])
                steps.append(float(s)*Unit(rng[3]))
                counts.append(int(floor(d/s+0.000000001))+1)
                others.append(keys)
            c['Pos'] = 0
            yield self.client.refresh()
            self.runSweep(c, sweepND(starts, steps, counts, others), self.client[server].settings[setting])
            returnValue(countND(counts))
        else:
            returnValue(0)

    @setting(50, 'Abort')
    def abort(self, c):
        """Abort the sweep currently running in this context."""
        if 'Busy' in c:
            c['Abort'] = defer.Deferred()
            return c['Abort']

    @setting(100, 'Wait')
    def wait(self, c):
        """Wait for the sweep surrently executing in this context to finish."""
        if 'Busy' in c:
            return c['Busy']

    # message notifications

    def signupForReport(self, c, name, messageID, active):
        """Add or remove a signup for a particular report message."""
        l = (c.source, messageID)
        if active:
            if l not in c[name]:
                c[name].append(l)
        else:
            if l in c[name]:
                c[name].remove(l)

    @setting(200, 'Report Progress', messageID=['w'], report=['b'])
    def report_progress(self, c, messageID, report=True):
        """Sign up for message notifications about sweep progress.

        The message will contain a single word indicating the number
        of points completed in the scan.
        """
        self.signupForReport(c, 'Progress', messageID, report)

    @setting(201, 'Report Completion', messageID=['w'], report=['b'])
    def report_completion(self, c, messageID, report=True):
        """Sign up for message notifications about sweep completion.

        The message will contain a boolean indicating whether the
        sweep completed successfully.
        """
        self.signupForReport(c, 'Completion', messageID, report)

    @setting(202, 'Report Errors', messageID=['w'], report=['b'])
    def report_errors(self, c, messageID, report=True):
        """Sign up for message notifications about sweep errors.

        The message will contain a string representing the error
        that occurred.
        """
        self.signupForReport(c, 'Errors', messageID, report)

    # misc

    @setting(1000, 'Test')
    def test(self, c):
        return dir(self.client._cxn)

    @setting(10000, 'Kill')
    def kill(self, c):
        """Kill this server."""
        reactor.callLater(0, reactor.stop)


__server__ = SweepServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
