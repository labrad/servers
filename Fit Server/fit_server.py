# Copyright (C) 2007  Matthew Neeley
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

"""
### BEGIN NODE INFO
[info]
name = Fit Server
version = 1.0.1
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, util
from labrad.server import LabradServer, setting, Signal
from labrad.util import hydrant
from labrad.types import Error

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

from fit_spectroscopy import *
import fit_squid_steps

import time
from datetime import datetime

class FitServer(LabradServer):
    """Fit Server is a general mathematics package for LabRad that does
    Qubit-relevant data fitting for automation purposes.
    """
    name = 'Fit Server'
    testMode = True

    def initServer(self):
        print 'initializing server'
    
    @inlineCallbacks
    def stopServer(self):
        pass

    @inlineCallbacks
    def get_data_at_path(self,c,path):
        dv = self.client.data_vault.packet()
        dv.cd(path[0])
        dv.open(path[1])
        dv.get(key='data')
        dv.get_parameter('Stats',key='stats')
        
        ans = yield dv.send()
        returnValue(ans)
        

    @setting(3,"Spectroscopy Fit",data=['(*{path}ss{file})','(*{path}sw{index})'],returns=['*(w{series}*{A,width,x0,noise}v)'])
    def fit_spectroscopy(self,c,data):
        """fit_spectroscopy fits the given dataset to a series of Lorenzians.  It
        only takes a pointer (needs parameters on the dataset) to where it can
        find the data in the data vault.  Either way, it recursively fits as few
        lorenzians as needed to "adequately" fit the data.  Returned is a list of
        fits, each with an index of the data series (1,2,3, etc... because 0 is the
        x-axis, the frequencies.) and an array of 4 values, in the following order:

            0: amplitude of the lorenzian
            1: the width of the lorenzian (gamma)
            2: x0, the center frequency
            3: noise, the baseline, noise level (usually 5-10% or whatever)

        Perhaps should return some actual quality values, as it stands now, you must
        calculate these yourself (chi-squared, etc.) """
        
        ## data is not the data, but is a path to the data
        ans = yield self.get_data_at_path(c,data)
        data = ans.data.asarray
        stats = ans.stats
        
        ret = []
        for i in range(1,data.shape[1]):
            fitobj = spectroscopy_data(data[:,0],data[:,i],stats)
            fitobj.fit()
            for fit in fitobj.fits:
                    ret.append((i,fit))

        returnValue(ret)
    
    @setting(4,"Squid Steps Fit",data=['(*{path}ss{file})','(*{path}sw{index})'],returns=['*((vv)(vv))'])
    def fit_squidsteps(self,c,data):
        ans = yield self.get_data_at_path(c,data)
        data = ans.data.asarray
        stats = ans.stats

        fitobj = fit_squid_steps.squid_fit(data[:,0],data[:,1],data[:,2],stats)
        fitobj.fit()

        ret = list()

        for line in fitobj.shared_lines:
            ret.append(((line[0,0],line[0,1]),(line[1,0],line[1,1])));

        returnValue(ret)

    @setting(5,"Step Edge Fit",data=['(*{path}ss{file})','(*{path}sw{index})'],returns=[''])
    def fit_stepedge(self,c,data):
        ans = yield self.get_data_at_path(c,data)
        data = ans.data.asarray
        
        fitobj = step_edge_fit(data[:,0],data[:,1])
        fitobj.fit()

        if fitobj.direction == 0:
            raise Error("No Direction",100)
        
##    @setting(2)
##    def delayed_echo(self, c, data):
##        """Echo a packet after a specified delay."""
##        yield util.wakeupCall(c['delay'])
##        returnValue(data)
##
##    @setting(3)
##    def delayed_echo_deferred(self, c, data):
##        """Echo a packet after a specified delay."""
##        d = defer.Deferred()
##        reactor.callLater(c['delay'], d.callback, data)
##        return d
##
##    @setting(4, delay=['v[s]', ''], returns=['v[s]'])
##    def echo_delay(self, c, delay):
##        """Get or set the echo delay."""
##        self.log('Echo delay: %s' % delay)
##        if delay is not None:
##            c['delay'] = float(delay)
##        return c['delay']
##
##    @setting(40, speed=['v[m/s]', ''], returns=['v[m/s]'])
##    def speed(self, c, speed):
##        """Get or set the speed."""
##        self.log('Speed: %s' % speed)
##        if speed is not None:
##            c['speed'] = speed
##        return c['speed']
##
##    @setting(41)
##    def verbose_echo(self, c, data):
##        print type(data)
##        print repr(data)
##        return data
##
##    @setting(5)
##    def exc_in_handler(self, c, data):
##        self.log('Exception in handler.')
##        raise Exception('Raised in handler.')
##
##    @setting(6)
##    def exc_in_subfunction(self, c, data):
##        self.log('Exception in subfunction.')
##        owie()
##
##    @setting(7)
##    def exc_in_deferred(self, c, data):
##        self.log('Exception in deferred.')
##        d = defer.Deferred()
##        d.addCallback(owie)
##        reactor.callLater(1, d.callback, None)
##        return d
##
##    @setting(8)
##    def exc_in_errback(self, c, data):
##        self.log('Exception from an errback.')
##        d = defer.Deferred()
##        reactor.callLater(1, d.errback, Exception('Raised by errback.'))
##        return d
##
##    @setting(9)
##    def exc_in_inlinecallback(self, c, data):
##        self.log('Exception from an inlineCallback.')
##        yield util.wakeupCall(c['delay'])
##        raise Exception('Raised in inlineCallback.')
##
##    @setting(10, returns=['s'])
##    def bad_return_type(self, c, data):
##        return 5
##        
##    @setting(11, tag=['s'])
##    def get_random_data(self, c, tag=None):
##        """Get a random bit of data conforming to the specified type tag."""
##        if tag is None:
##            t = hydrant.randType()
##        else:
##            t = T.parseTypeTag(tag)
##        return hydrant.randValue(t)
##        
##    @setting(12)
##    def get_random_tag(self, c, tag):
##        """Get a random LabRAD type tag."""
##        return str(hydrant.randType())

def owie(dummy=None):
    raise Exception('Raised in subfunction.')
        
__server__ = FitServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
