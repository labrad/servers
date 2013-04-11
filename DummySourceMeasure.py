#!/usr/bin/python

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T
from labrad.server import LabradServer, setting
import numpy as np
from labrad.units  import Unit, mV, mA, Ohm, nA, ns, deg, MHz, V, GHz, rad

class Diode(object):
    def __init__(self, Is=1*nA, n=1.6, Rs=0*Ohm):
        self.Is = Is
        self.n = n
        self.Rs = Rs
        self.Vt = 25.8*mV
    def IV(self, I, minV, maxV):
        #I = self.Is*(np.exp((maxV/(self.n*self.Vt))['']) - 1)
        V = self.Vt*np.log(((I+self.Is)/self.Is)[''])*self.n + I*self.Rs
        print "calculated V:", V
        if minV < V < maxV:
            return (I, V)
        elif V < minV or np.isnan(V):
            I = self.Is * (np.exp((minV / (self.Vt*self.n))['']) - 1)
            return (I, minV)
        else:
            I = self.Is * (np.exp((maxV / (self.Vt*self.n))['']) - 1)
            return (I, maxV)
            

class Resistor(object):
    def __init__(self, R=1*Ohm):
        self.R = R
    def IV(self, I, minV, maxV):
#        if minV['V'] > 0 or maxV['V'] < 0:
#            raise RuntimeError("zero volts must be in range")
        V = I * self.R
        if minV < V < maxV:
            return (I, V)
        elif V < minV:
            return (minV/self.R, minV)
        else:
            return (maxV/self.R, maxV)

        
class DummySourceMeasure(LabradServer):
    name = "Dummy Source Measure Server"
    @inlineCallbacks
    def initServer(self):
        print "a"
        nodename = util.getNodeName()
        print "b"
        path = ['', 'Servers', self.name]
        print "c"
        reg = self.client.registry
        p = reg.packet()
        p.cd(path)
        p.get("device", 's')
        ans = yield p.send()
        device_type = ans.get
        self.device = Diode()
        self.maxV = 0 * mV
        self.minV = 0 * mV
        self.I = 0 * mA

    @setting(10, volts=["v[mV]: set voltage upper limit"], returns='')
    def set_Vmax(self, c, volts):
        self.maxV = volts
    
    @setting(11, volts=["v[mV]: set voltage lower limit"], returns='')
    def set_Vmin(self, c, volts):
        self.minV = volts

    @setting(15, returns='v[mV]')
    def measure_v(self, c):
        (I,V) = self.device.IV(self.I, self.minV, self.maxV)
        return V.inUnitsOf('mV')
    
    @setting(20, current=["v[mA]: set output current"], returns='')
    def set_current(self, c, current):
        self.I = current

    @setting(25, returns='v[mA]')
    def measure_i(self, c):
        (I,V) = self.device.IV(self.I, self.minV, self.maxV)
        return I.inUnitsOf('mA')

__server__ = DummySourceMeasure()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
    
