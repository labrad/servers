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
from labrad.units  import us, mV

from twisted.python         import log
from twisted.internet       import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

PIPELINE_DEPTH = 5

class ContextBusyError(T.Error):
    """The context is currently busy"""
    code = 1

def NDsweeper(axes):
    if len(axes):
        axis = axes[0]
        cur = axis[0]
        end = axis[1]
        stp = abs(axis[2])
        if cur>end:
            while cur>=end:
                for l in NDsweeper(axes[1:]):
                    yield [(cur, axis[3:])] + l
                cur-=stp
        else:
            while cur<=end:
                for l in NDsweeper(axes[1:]):
                    yield [(cur, axis[3:])] + l
                cur+=stp
    else:
        yield []

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
            result = result.aslist
            if len(result)>0:
                if isinstance(result[0], list):
                    result=[sweepvars+res for res in result]
                else:
                    result=sweepvars+result
                yield self.client.data_vault.add(result, context=c.ID)
        except Exception, e:
            c['Exception']=e


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
        if 'Abort' in c:
            c['Abort'].callback(None)
            del c['Abort']
        del c['Busy']
        

    @setting(1, 'Repeat', server=['s'], setting=['s'], count=['w'], updatemessage=['(w,b)', '(w,w)'])
    def repeat(self, c, server, setting, count, updatemessage=None):
        if 'Busy' in c:
            raise ContextBusyError()
        c['Busy'] = True
        if 'Exception' in c:
            del c['Exception']
        self.runSweep(c, NDsweeper([[1,count,1]]), self.client[server].settings[setting])
        print "done"
        

    @setting(2, 'Sweep 1D', sweeprange=['vvv'], keys=['*(*ss)'], server=['s'],
                            setting=['s'], updatemessage=['(w,b)', '(w,w)'])
    def sweep1d(self, c, sweeprange, keys, server, setting, updatemessage=None):
        if 'Busy' in c:
            raise ContextBusyError()
        c['Busy'] = True
        if 'Exception' in c:
            del c['Exception']
        self.runSweep(c, NDsweeper([list(sweeprange)+keys.aslist]), self.client[server].settings[setting])
        

    @setting(3, 'Sweep 2D', sweeprangex=['vvv'], keysx=['*(*ss)'], sweeprangey=['vvv'], keysy=['*(*ss)'],
                            server=['s'], setting=['s'], updatemessage=['(w,b)', '(w,w)'])
    def sweep2d(self, c, sweeprangex, keysx, sweeprangey, keysy, server, setting, updatemessage=None):
        if 'Busy' in c:
            raise ContextBusyError()
        c['Busy'] = True
        if 'Exception' in c:
            del c['Exception']
        self.runSweep(c, NDsweeper([list(sweeprangex)+keysx.aslist, list(sweeprangey)+keysy.aslist]), self.client[server].settings[setting])
        

    @setting(4, 'Sweep ND', sweeprangesandkeys=['*((vvv)*(*ss))'], server=['s'],
                            setting=['s'], count=['w'], updatemessage=['(w,b)', '(w,w)'])
    def sweepnd(self, c, sweeprangesandkeys, server, setting, count, updatemessage=None):
        if 'Busy' in c:
            raise ContextBusyError()
        c['Busy'] = True
        if 'Exception' in c:
            del c['Exception']
        l = [list(sak[0])+sak[1].aslist for sak in sweeprangesandkeys]
        self.runSweep(c, NDsweeper(l), self.client[server].settings[setting])


    @setting(100, 'Abort')
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
