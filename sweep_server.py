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

PIPELINE_DEPTH = 5

class ContextBusyError(T.Error):
    """The context is currently busy"""
    code = 1

def rangeND(limits):
    if len(limits):
        cur = [0]*len(limits)
        while cur[0]<limits[0]:
            yield [c for c in cur]
            a=len(limits)-1
            cur[a]+=1
            while (a>0) and (cur[a]==limits[a]):
                cur[a]=0
                a-=1
                cur[a]+=1

def countND(limits):
    if len(limits):
        c = 1
        for l in limits:
            c*=l
        return c
    else:
        return 0

def sweepND(starts, steps, counts, pars):
    for cur in rangeND(counts):
        pos = [start+step*count for start,step,count in zip(starts,steps,cur)]
        yield zip(pos, pars)

class SweepServer(LabradServer):
    name = 'Sweep Server'
    sendTracebacks = False

    def initServer(self):
        self.Contexts=[]
        

    @inlineCallbacks
    def runPoint(self, c, regpkt, setting, semaphore, sweepvars):
        try:
            if len(self.Contexts):
                ctxt = self.Contexts.pop()
            else:
                ctxt = self.client.context()
            try:
                yield regpkt.send(context=ctxt)
                result = yield setting(c.ID, context=ctxt)
            finally:
                self.Contexts.append(ctxt)
                semaphore.release()
            c['Pos']+=1
            if 'Progress' in c:
                for tgt, msg in c['Progress']:
                    self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, long(c['Pos']))]) 
            result = result.aslist
            if len(result)>0:
                if isinstance(result[0], list):
                    result=[sweepvars+res for res in result]
                else:
                    result=sweepvars+result
                yield self.client.data_vault.add(result, context=c.ID)
        except Exception, e:
            if 'Exception' not in c:
                c['Exception']=e
                if 'Errors' in c:
                    for tgt, msg in c['Errors']:
                        self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, repr(e))]) 


    @inlineCallbacks
    def runSweep(self, c, sweeper, setting):
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
        if 'Completion' in c:
            b = True
            if 'Abort' in c:
                b=False;
            if 'Exception' in c:
                b=False;
            for tgt, msg in c['Completion']:
                self.client._cxn.sendPacket(tgt, c.ID, 0, [(msg, b)]) 
        

    @setting(1, 'Repeat', server=['s'], setting=['s'], count=['w'])
    def repeat(self, c, server, setting, count):
        if 'Busy' in c:
            raise ContextBusyError()
        c['Busy'] = defer.Deferred()
        if 'Exception' in c:
            del c['Exception']
        c['Pos']=0
        yield self.client.refresh()
        self.runSweep(c, NDsweeper([[1,count,1]]), self.client[server].settings[setting])
        print "done"
        

    @setting(10, 'Simple Sweep', server=['s'], setting=['s'], sweeprangesandkeys=['*((vvvs)*(*ss))'], returns=['w'])
    def simple_sweep(self, c, server, setting, sweeprangesandkeys):
        if 'Busy' in c:
            raise ContextBusyError()
        if len(sweeprangesandkeys):
            c['Busy'] = defer.Deferred()
            if 'Exception' in c:
                del c['Exception']
            starts=[]
            steps =[]
            counts=[]
            others=[]
            for rng, keys in sweeprangesandkeys:
                starts.append(float(rng[0])*Unit(rng[3]))
                d = rng[1]-rng[0]
                if d<0:
                    s = -abs(rng[2])
                else:
                    s = abs(rng[2])
                steps.append(float(s)*Unit(rng[3]))
                counts.append(int(floor(d/s+0.000000001))+1)
                others.append(keys)
            c['Pos']=0
            yield self.client.refresh()
            self.runSweep(c, sweepND(starts, steps, counts, others), self.client[server].settings[setting])
            returnValue(countND(counts))
        else:
            returnValue(0)

    @setting(100, 'Wait')
    def wait(self, c):
        if 'Busy' in c:
            return c['Busy']

    @setting(1000, 'Test')
    def test(self, c):
        return dir(self.client._cxn)

    @setting(200, 'Report Progress', messageID=['w'], report=['b'])
    def report_progress(self, c, messageID, report=True):
        l = (c.source, messageID)
        if report:
            if 'Progress' not in c:
                c['Progress']=[l]
            else:
                if l not in c['Progress']:
                    c['Progress'].append(l)
        else:
            if 'Progress' in c:
                if l in c['Progress']:
                    c['Progress'].remove(l)

    @setting(201, 'Report Completion', messageID=['w'], report=['b'])
    def report_completion(self, c, messageID, report=True):
        l = (c.source, messageID)
        if report:
            if 'Completion' not in c:
                c['Completion']=[l]
            else:
                if l not in c['Completion']:
                    c['Completion'].append(l)
        else:
            if 'Completion' in c:
                if l in c['Completion']:
                    c['Completion'].remove(l)

    @setting(202, 'Report Errors', messageID=['w'], report=['b'])
    def report_errors(self, c, messageID, report=True):
        l = (c.source, messageID)
        if report:
            if 'Errors' not in c:
                c['Errors']=[l]
            else:
                if l not in c['Errors']:
                    c['Errors'].append(l)
        else:
            if 'Errors' in c:
                if l in c['Errors']:
                    c['Errors'].remove(l)


    @setting(50, 'Abort')
    def abort(self, c):
        if 'Busy' in c:
            c['Abort'] = defer.Deferred()
            return c['Abort']


    @setting(10000, 'Kill')
    def kill(self, c):
        reactor.callLater(0, reactor.stop)

        

__server__ = SweepServer()

if __name__ == '__main__':
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
    except ImportError:
        pass
    from labrad import util
    util.runServer(__server__)
