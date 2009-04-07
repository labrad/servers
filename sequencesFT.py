from numpy import exp, log, pi, sin, cos, sqrt, arange, sinc, linspace, real, imag
from numpy.fft import ifft
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

    def __rmul__(self, other):
        if callable(other):
            return pulseClass(lambda x: self.pulsefunc(x) * other(x))
        else:
            return pulseClass(lambda x: self.pulsefunc(x) * other)

    __lmul__ = __rmul__


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


def zPulse(start, length, amplitude, sbfreq=0.0,overshoot=0.0):
    """Abrupt jumps from 0 to amplitude and back."""
    start = start + 0.5*length
    amplitude = nounits(amplitude)
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
