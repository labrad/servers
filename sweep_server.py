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
import operator
import numpy

REGISTRY_PATH = ['', 'Servers', 'Sweep Server']
DEFAULT_PIPE_DEPTH = 8

class ContextBusyError(T.Error):
    """The context is currently busy"""
    code = 1
    
def rangeND(limits):
    """Iterate over an N-dimensional set of limits."""
    if len(limits):
        cur = [0] * len(limits)
        while cur[0] < limits[0]:
            yield list(cur)
            a = len(limits) - 1
            cur[a] += 1
            while (a > 0) and (cur[a] == limits[a]):
                cur[a] = 0
                a -= 1
                cur[a] += 1

def sweepND(starts, steps, counts, keys):
    """An N-dimensional iterator where each axis goes from start up by step."""
    for cur in rangeND(counts):
        values = [start + step * count for start, step, count in zip(starts, steps, cur)]
        yield zip(values, keys)
            
class SweepServer(LabradServer):
    """Allows the user to run sweeps by calling a server setting repeatedly
    while changing the values of parameters stored in the Registry.  The
    server implements pipelining, making each call in a separate context
    with the appropriate registry context being duplicated and then using
    registry overrides to update keys for the sweep itself.
    """
    name = 'Sweep Server'
    sendTracebacks = False

    @inlineCallbacks
    def initServer(self):
        self.contextPool = set()
        # load settings and listen for changes
        self._regCtx = self.client.context()
        yield self.loadSettings()
        def registryChanged(c, msg):
            return self.loadSettings()
        self.client._addListener(registryChanged, ID=234, context=self._regCtx)
        self.client.registry.notify_on_change(234, True, context=self._regCtx)
        
    @inlineCallbacks
    def loadSettings(self):
        """Load settings from the registry."""
        reg = self.client.registry
        p = reg.packet(context=self._regCtx)
        p.cd(REGISTRY_PATH, True)
        p.dir()
        ans = yield p.send()
        dirs, keys = ans.dir
        if 'Pipe Depth' not in keys:
            yield reg.set('Pipe Depth', DEFAULT_PIPE_DEPTH, context=self._regCtx)
        self.pipeDepth = yield reg.get('Pipe Depth', context=self._regCtx)
        print 'Default Pipe Depth =', self.pipeDepth
        
    def initContext(self, c):
        c['Progress'] = []
        c['Completion'] = []
        c['Errors'] = []
        c['Data'] = []
        
    @inlineCallbacks
    def runPoint(self, c, setting, semaphore, regPkt, sweepVars, sendToDataVault=True):
        """Run a single point in a sweep."""
        try:
            try:
                if len(self.contextPool):
                    ctxt = self.contextPool.pop()
                else:
                    ctxt = self.client.context()
                yield regPkt.send(context=ctxt)
                result = yield setting(c.ID, context=ctxt)
            finally:
                self.contextPool.add(ctxt)
                semaphore.release()
            c['Pos'] += 1
            self.notifyAll(c, 'Progress', long(c['Pos']))
            result = result.asarray
            if len(result):
                if len(result.shape) != 1:
                    sweepVars = numpy.tile([sweepVars], (result.shape[0], 1))
                result = numpy.hstack((sweepVars, result))
                if sendToDataVault:
                    yield self.client.data_vault.add(result, context=c.ID)
                self.notifyAll(c, 'Data', result)
        except Exception, e:
            if 'Exception' not in c:
                c['Exception'] = e
                self.notifyAll(c, 'Errors', str(e))

    def buildRegistryPacket(self, c, sweep):
        """Build a packet to update registry keys for a sweep point."""
        p = self.client.registry.packet()
        p.duplicate_context(c.ID)
        for value, keys in sweep:
            for path, key in keys:
                if len(path):
                    p.cd(path)
                    p.override(key, value)
                    p.cd(len(path))
                else:
                    p.override(key, value)
        return p
                
    @inlineCallbacks
    def runSweep(self, c, sweeper, setting, sendToDataVault=True):
        """Run a sweep."""
        depth = self.pipeDepth
        semaphore = defer.DeferredSemaphore(depth)
        for sweep in sweeper:
            if ('Abort' in c) or ('Exception' in c):
                break
            regPkt = self.buildRegistryPacket(c, sweep)
            values = [value for value, keys in sweep]
            yield semaphore.acquire()
            self.runPoint(c, setting, semaphore, regPkt, values, sendToDataVault)
        # make sure the sweep is done by acquiring every stage
        for a in range(depth):
            yield semaphore.acquire()
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
        self.notifyAll(c, 'Completion', b)
        
    @setting(10, 'Simple Sweep', server='s', setting='s',
                                 sweepRangesAndKeys='*((vvvs)*(*ss))',
                                 sendToDataVault='b',
                                 returns='w')
    def simple_sweep(self, c, server, setting, sweepRangesAndKeys, sendToDataVault=True):
        """Run a simple sweep.

        The specified setting on the specified server will be called for
        each point in the sweep.  
        """
        if 'Busy' in c:
            raise ContextBusyError()
        if 'Exception' in c:
            del c['Exception']
        if not len(sweepRangesAndKeys):
            returnValue(0)
        c['Busy'] = defer.Deferred()
        c['Pos'] = 0
        starts, steps, counts, others = [], [], [], []
        for (start, stop, step, unit), keys in sweepRangesAndKeys:
            d = stop - start
            s = abs(step) if d >= 0 else -abs(step)
            u = Unit(unit)
            starts.append(float(start) * u)
            steps.append(float(s) * u)
            counts.append(int(floor(d / s + 0.000000001))+1)
            others.append(keys)
        # TODO: remove this next line as soon as we have auto-refreshing clients
        yield self.client.refresh()
        sweeper = sweepND(starts, steps, counts, others)
        func = self.client[server].settings[setting]
        self.runSweep(c, sweeper, func, sendToDataVault)
        # number of points is the product of the counts
        total = reduce(operator.mul, counts)
        returnValue(total)

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
        target = (c.source, messageID)
        if active:
            if target not in c[name]:
                c[name].append(target)
        else:
            if target in c[name]:
                c[name].remove(target)
                
    def notifyAll(self, c, name, data):
        """Send a message to everyone listening on a particular message."""
        for tgt, msg in c[name]:
            self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, data)])

    @setting(200, 'Report Progress', messageID='w', report='b')
    def report_progress(self, c, messageID, report=True):
        """Sign up for message notifications about sweep progress.

        The message will contain a single word indicating the number
        of points completed in the scan.
        """
        self.signupForReport(c, 'Progress', messageID, report)

    @setting(201, 'Report Completion', messageID='w', report='b')
    def report_completion(self, c, messageID, report=True):
        """Sign up for message notifications about sweep completion.

        The message will contain a boolean indicating whether the
        sweep completed successfully.
        """
        self.signupForReport(c, 'Completion', messageID, report)

    @setting(202, 'Report Errors', messageID='w', report='b')
    def report_errors(self, c, messageID, report=True):
        """Sign up for message notifications about sweep errors.

        The message will contain a string representing the error
        that occurred.
        """
        self.signupForReport(c, 'Errors', messageID, report)
        
    @setting(203, 'Report Data', messageID='w', report='b')
    def report_data(self, c, messageID, report=True):
        """Sign up for messages containing sweep data.
        
        The message will contain data as it would be sent to the
        data vault, with sweep variables followed by results
        from the setting called.
        """
        self.signupForReport(c, 'Data', messageID, report)

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
