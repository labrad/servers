import math

import numpy
from numpy import exp, log, pi, sin, cos, sqrt, arange, sinc, linspace, real, imag
#from numpy.fft import ifft
##import pylab

# sequences and sequence creation functions in Fourier representation

def nounits(x):
    if hasattr(x,'value'):
        return x.value
    else:
        return x


class pulseClass():
    def __init__(self, pulsefunc):
        self.pulsefunc = pulsefunc

    def __call__(self, x):
        return self.pulsefunc(x)

    def __radd__(self, other):
        if callable(other):
            return pulseClass(lambda x: self.pulsefunc(x) + other(x))
        else:
            return pulseClass(lambda x: self.pulsefunc(x) + other)

    __ladd__ = __radd__
    __iadd__ = __radd__

    def __rmul__(self, other):
        if callable(other):
            return pulseClass(lambda x: self.pulsefunc(x) * other(x))
        else:
            return pulseClass(lambda x: self.pulsefunc(x) * other)

    __lmul__ = __rmul__
    __imul__ = __rmul__


NOTHING = pulseClass(lambda f: 0 * f)

def measureTrace(start, length, amplitude):
    """Abrupt step from 0 to amplitude, followed by triangular ramp down of given length."""
    #starting at 2008/06/31 measure traces are triangular
    if abs(length) < 1e-3:
        return pulseClass(lambda f: amplitude*exp(-2j*pi*f*start))
    def trace(f):
        z = f == 0
        f = 2j*pi*(f + z)
        return  nounits(amplitude)  * (exp(-f*start) * \
            (1-z) * (1.0/f - (1-exp(-f*length))/length/(f**2)) \
            + 0.5*length * z)
    return pulseClass(trace)


# gaussian pulse trace creation functions
def gaussian_envelope(t0, w, amplitude=1.0, sbfreq=0.0, phase=0.0):
    """Create an envelope function for a gaussian pulse.

    The pulse is centered at t0, has a FWHM of w, and a specified phase.
    """
    w = 0.5*pi*w/sqrt(log(2))
    amplitude = nounits(amplitude)*w / sqrt(pi)
    amplitude *= exp(-1j*phase) # Not sure about sign convention
    
    return pulseClass(lambda f: amplitude \
                                * exp(-2j*pi*(f+sbfreq)*t0) \
                                * exp(-(w*(f+sbfreq))**2) )

gaussian = gaussian_envelope

def zPulse(start, length, amplitude, sbfreq=0.0, overshoot=0.0, phase=0.0):
    """Abrupt jumps from 0 to amplitude and back."""
    start = start + 0.5*length
    amplitude = nounits(amplitude) * exp(-1j*phase)
    overshoot = nounits(overshoot)
    return pulseClass(lambda f: exp(-2j*pi*(f+sbfreq)*start) \
        * amplitude * abs(length) * sinc(length*(f+sbfreq)) + \
                      overshoot * (exp(-2j*pi*(f+sbfreq)*(start-0.5*length)) + \
                                   exp(-2j*pi*(f+sbfreq)*(start+0.5*length))))


def flattop(start, length, width, amplitude=1.0, sbfreq=0.0):
    """Smoothed z-pulse by convolving with Gaussian with given width"""
    return zPulse(start, length, 2.0/width*sqrt(log(2)/pi), sbfreq = sbfreq) * \
           gaussian_envelope(0, width, amplitude=amplitude, sbfreq = sbfreq)
    

def parabola(start, length, height):
    def pulsefunc(f):
        nu = pi * f
        nu0 = nu == 0
        nu += nu0
        return 2.0/3.0*height*length*nu0 + \
            (1-nu0)* exp(-2j*nu*(start+0.5*length)) * 2 * height/length/nu**2 * \
            (sin(length * nu)/(length*nu)-cos(length*nu))
    return pulseClass(pulsefunc)

    
def rampPulse(start, ramptime, flattime, height):
    """Ramp up, hold and then ramp back down."""
    start += ramptime
    return measureTrace(start, -ramptime, -height) \
        +  measureTrace(start+flattime, ramptime, height) \
        + zPulse(start, flattime, height)

    
def rampPulse2(start, flattime, ramptime, height):
    """Hold and then ramp back down."""
    return measureTrace(start+flattime, ramptime, height) \
         + zPulse(start, flattime, height)


##def plotSequence(func,t0=-200,n=1000):
##    f = linspace(0.5,1.5, n, endpoint=False) % 1 - 0.5
##    signal = func(f) * exp(2.0j*pi*t0*f)
##    signal = ifft(signal)
##    t = t0 + arange(n)
##    pylab.plot(t,real(signal))
##    pylab.plot(t,imag(signal))
##    



## Sequences server

from labrad.server import LabradServer, setting
from labrad.units  import Unit, mV, ns, deg, rad, MHz, GHz

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

"""
### BEGIN NODE INFO
[info]
name = Sequences FFT
version = 1.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

class SequenceServer(LabradServer):
    name = 'Sequences FFT'

    def initContext(self, c):
        c['iqs'] = {}
        c['analogs'] = {}
        for key in ['tmin', 'tmax', 'seq']:
            if key in c:
                del c[key]
    
    def updateMinMax(self, c, tmin, tmax):
        tmin, tmax = min(tmin, tmax), max(tmin, tmax)
        c['tmin'] = min(tmin, c['tmin']) if 'tmin' in c else tmin
        c['tmax'] = max(tmax, c['tmax']) if 'tmax' in c else tmax

        
    @setting(1, 'Add IQ Channel', channel='sw')
    def add_iq_channel(self, c, channel):
        c['seq'] = c['iqs'][channel] = NOTHING
    
    @setting(2, 'Add Analog Channel', channel='sw')
    def add_analog_channel(self, c, channel):
        c['seq'] = c['analogs'][channel] = NOTHING
    
    @setting(10, 'Add Gaussian',
             t0='v[ns]', w='v[ns]', amplitude='v', sbfreq='v[GHz]', phase='v[rad]',
             returns='')
    def add_gaussian(self, c, t0, w, amplitude, sbfreq, phase=0.0):
        c['seq'] += gaussian(float(t0), float(w), float(amplitude), float(sbfreq), float(phase))
        self.updateMinMax(c, t0 - 2*w, t0 + 2*w)


    @setting(20, 'Add Ramp Pulse 2',
             start='v[ns]', flattime='v[ns]', ramptime='v[ns]', height='v',
             returns='')
    def add_rampPulse2(self, c, start, flattime, ramptime, height):
        c['seq'] += rampPulse2(float(start), float(flattime), float(ramptime), float(height))
        self.updateMinMax(c, start, start + flattime + ramptime)

    
    @setting(30, 'Add Flattop',
             start='v[ns]', length='v[ns]', width='v[ns]', amplitude='v', sbfreq='v[GHz]',
             returns='')
    def add_flattop(self, c, start, length, width, amplitude, sbfreq):
        c['seq'] += flattop(float(start), float(length), float(width), float(amplitude), float(sbfreq))
        self.updateMinMax(c, start - width, start + length + width)
    
    
    @setting(40, 'Add zPulse',
             start='v[ns]', length='v[ns]', amplitude='v', sbfreq='v[GHz]', phase='v[rad]', overshoot='v',
             returns='')
    def add_zpulse(self, c, start, length, amplitude, sbfreq, phase=0.0, overshoot=0.0):
        c['seq'] += zPulse(float(start), float(length), float(amplitude), float(sbfreq), float(overshoot), float(phase))
        self.updateMinMax(c, start, start + length)
    
    
    @setting(50, 'Upload', padding=['v[ns]', 'v[ns] v[ns]'])
    def upload(self, c, padding):
        if not isinstance(padding, tuple):
            padding = (padding, padding)
        t0 = c['tmin'] - float(padding[0])
        t1 = c['tmax'] + float(padding[1])
        p = self.client.qubits.packet(context=c.ID)
        for ch, seq in c['iqs'].items():
            p.experiment_use_fourier_deconvolution(ch, t0)
            p.sram_iq_data(ch, seq(uwFreqs(t1 - t0)), tag='(sw)*c')
        for ch, seq in c['analogs'].items():
            p.experiment_use_fourier_deconvolution(ch, t0)
            p.sram_analog_data(ch, seq(mpFreqs(t1 - t0)), tag='(sw)*v')
        yield p.send()
        self.initContext(c)
    


    @setting(100000, 'Kill')
    def kill(self, c, context):
        reactor.callLater(1, reactor.stop)


def mpFreqs(seqTime=1024):
    nfft = 2**(math.ceil(math.log(seqTime, 2)))
    return numpy.linspace(0, 0.5, nfft/2+1, endpoint=True)

def uwFreqs(seqTime=1024):
    nfft = 2**(math.ceil(math.log(seqTime, 2)))
    return numpy.linspace(0.5, 1.5, nfft, endpoint=False) % 1 - 0.5

__server__ = SequenceServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
