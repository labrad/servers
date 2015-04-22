# Copyright (C) 2007-2009 Max Hofheinz
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


import numpy as np

# CHANGELOG
#
# 2012 April 12 - Jim Wenner
#
# Changed logic string in setSettling from np.any(self.decayRates!=rates)
# to not (np.array_equal(self.decayRates,rates). With any(!=), if
# self.decayRates is empty, the output will be an empty array and not
# False, so the section to change self.decayRates is not entered.

# CHANGELOG
#
# 2013 April/May - R. Barends
#
# Changes in Z board (Single) DAC calibration:
#
# Rewrote LoadCal to be more intelligible
#
# Introduced cutoff frequency. This is necessary because high frequency signals in the correction window have a bad S/N ratio. 
# In addition, the way the impulse response is calculated suppresses 1 GHz noise, but amplifies 500 MHz. Default value is to cut off at 450 MHz. Keep it above 350 MHz.
# Also, these high frequencies tend to give rise to long oscillations in the deconvolved timetrace, messing up dualblock.
#
# Truncation of large correction factors in the fourier domain: the correction window can have very large amplitudes (and low S/N), 
# therefore the time domain signal can have large oscillations which will be truncated digitally, leading to deterioration of the waveform.
# Now, a maximum value is enforced in the fourier domain. The value is truncated but the phase is kept.
# This way we still have a partial correction, within the limits of the boards. Doing it this way also ensures that the waveforms are scalable.
#
# Cubic interpolation for the fourier transform. It visually reduced the ringing on the scope. Cubic interpolation algorithm is as fast as linear interpolation.
#
# The deconv now does NOT shift the timetrace. This arose from the rise being at t=10-20 ns, instead of t=0. 
# However, this leads to the timetrace running out of its intendend memory block. In addition, the phase varies more slowly, easing interpolation.
#
# Fixed logical bug in setSettling
#
# Enforces borderValues at first and last 4 points. The deconvolved signal can be nonzero at the start and end of a sequence.
# This nonzero value persists, even when running the board with an empty envelope. Hence, the Z bias is in a small-valued but arbitrary state after each run, 
# possibly even oscillating, if the 4 last values are not identical. To remove this, the last 4 (FOUR) values are set to 0.0.
# For dualblock, there is a function 'set_border_values' to set the bordervalues. Be sure to set it for both the first and last block, in fpgaseqtransmon.
#
#
# Changes to IQ board DAC calibration:
#
# Enforces zeros at first and last 4 points. The deconvolved signal can be nonzero at the start and end of a sequence.
# This nonzero value persists, even when running the board with an empty envelope. To remove this, the last 4 (FOUR) values must be set.
#
# Cubic interpolation for zero value
#
# Removed a tab

def cosinefilter(n, width=0.4):
    """cosinefilter(n,width) cosine lowpass filter
    n samples from 0 to 1 GHz
    1 from 0 GHz to width GHz
    rolls of from width GHz to 0.5 GHz like a quater cosine wave"""
    nr = n/2 + 1
    result = np.ones(nr,dtype=float)
    start = int(np.ceil(width*n))
    width = (0.5-width)*n
    if start < nr:
        result[start:] = 0.5+0.5*np.cos(
            np.linspace(np.pi * (start-0.5*n+width) / width,
                           np.pi + np.pi / width*(nr-0.5*n),
                           nr-start, endpoint=False))
    return result


def gaussfilter(n, width=0.13):
    """lowpassfilter(n,width) gaussian lowpass filter.
    n samples from 0 to 1 GHz
    -3dB frequency at width GHz
    """
    nr = n/2 + 1
    x = 1.0 / width * np.sqrt(np.log(2.0)/2.0)
    gauss = np.exp(-np.linspace(0, x*nr/n, nr, endpoint=False)**2)
    x = np.exp(-(0.5*x)**2)
    gauss -= x
    gauss /= (1.0 - x)
    return gauss
    
    
def flatfilter(n, width=0):
    nr = n/2 + 1
    return 1.0
    #return np.ones(nr)

    
savedfftlens = np.zeros(8193,dtype=int)
    

def fastfftlen(n):
    """
    Computes the smallest multiple of 2 3 and 5 larger or equal n.
    FFT is fastest for sizes that factorize in small numbers.
    Sizes up to 8192 are only calculated once and later looked up.
    """
    def _fastfftlen(n):
        logn = np.log(n)
        n5 = 5L ** np.arange(long(logn/np.log(5.) + 2. + 1.e-6))
        n3 = 3L ** np.arange(long(logn/np.log(3.) + 2. + 1.e-6))
        n35 = np.outer(n3, n5).flat
        n35 = np.compress(n35<2*n, n35)
        n235 = ((-np.log(n35)+logn)/np.log(2.) + 0.999999).astype(int)
        n235 *= (n235>0)
        n235 = 2**n235 * n35
        return np.min(n235)
    
    if n < np.alen(savedfftlens):
        nfft = savedfftlens[n]
        if nfft < n:
            nfft = _fastfftlen(n)
            savedfftlens[n] = nfft
        return nfft
    else:
        return _fastfftlen(n)
    
def moving_average(x,m):
    """Moving average on x, with length m. Expects a numpy array for x. Elements are given by
    y[i] = Sum_{k=0..m-1}   y[l] / m
    with l=i-fix(m/2)+k between 0 and length(x)-1. Try to keep m odd. RB."""
    n=np.alen(x)
    before=-np.fix(int(m)/2.0)
    y=[]
    for i in np.arange(len(x)):
        a=0.0
        for tel in np.arange(int(m)):
            idx=i+before+tel
            if idx<0:
                idx=0
            elif idx>=n:
                idx=n-1
            a += x[idx]/np.float(m)
        y.append(a)
    return np.array(y)


def derivative(x,y):
    """Taking derivative, uses both adjacent points for estimate of derivative. 
    Returns array with the same number of points (different than np.diff). RB."""
    n=np.alen(x)
    deriv=np.array(np.linspace(0.0,0.0,n),dtype=complex)
    for k in np.arange(n):
        if k==0:
            deriv[k]=1.0*(y[k+1]-y[k])/(x[k+1]-x[k])
        elif k==(n-1):
            deriv[k]=1.0*(y[k]-y[k-1])/(x[k]-x[k-1])
        else:
            deriv[k]=1.0*(y[k+1]-y[k-1])/(x[k+1]-x[k-1])
    return deriv


def interpol_cubic(h,x2,fill_value=None):
    """Fast cubic interpolator (slightly faster than linear version of scipy interp1d; 
    much faster than cubic version of scipy interp1d).
    Returns the values in in the same way interpol. Can deal with complex input.
    Uses linear interpolation at the edges, and returns the values at the edges outside of the range. RB."""
    xlen=np.alen(h)
    if type(h) is not np.ndarray:
        #we need a numpy array
        h=1.0*np.array(h)
    def func(xdet):
        if type(xdet) is not list and type(xdet) is not np.ndarray:
            xdet=np.array([xdet]) 
        yout=np.zeros(np.alen(xdet)).astype(h.dtype) #predefine
        x2=xdet  #x2 = (xdet-xstart) #map xdet onto h index: x ->   (x-xstart)/dx = 0... length
        
        #indices outside of the range
        xdet_idx = x2<0 #maps which index in x2 it is
        if xdet_idx.any():       
            x2_idx = x2[ xdet_idx ] #maps x2 to x index
            h_idx = np.array(x2_idx).astype(int) #maps which h,x to take
            if fill_value is None:
                yout[xdet_idx]=h[0]
            else:
                yout[xdet_idx]=fill_value
        xdet_idx = x2>(xlen-1) #maps which index in x2 it is
        if xdet_idx.any():       
            x2_idx = x2[ xdet_idx ] #maps x2 to x index
            h_idx = np.array(x2_idx).astype(int) #maps which h,x to take
            if fill_value is None:            
                yout[xdet_idx]=h[xlen-1]
            else:
                yout[xdet_idx]=fill_value                
            
        #indices on the rim: linear interpolation
        xdet_idx =  np.logical_and(x2>=0,x2<1) #maps which index in x2 it is
        if xdet_idx.any():
            x2_idx = x2[ xdet_idx ] #maps x2 to x index
            h_idx = np.array(x2_idx).astype(int) #maps which h,x to take        
            yout[xdet_idx]=(h[1]-h[0])*x2_idx  + h[0]
        xdet_idx =  np.logical_and(x2>=(xlen-2),x2<=(xlen-1)) #maps which index in x2 it is
        if xdet_idx.any():
            x2_idx = x2[ xdet_idx ] #maps x2 to x index
            h_idx = np.array(x2_idx).astype(int) #maps which h,x to take        
            yout[xdet_idx]=(h[xlen-1]-h[xlen-2])*(x2_idx-h_idx[0])  + h[xlen-2]
            
        #indices inside the range: cubic interpolation        
        xdet_idx = np.logical_and(x2>=1,x2<(xlen-2)) #maps which index in x2 it is
        if xdet_idx.any():        
            x2_idx = x2[ xdet_idx ] #maps x2 to x index
            h_idx = np.array(x2_idx).astype(int) #maps which h,x to take
            hp2=h[h_idx+2]
            hp1=h[h_idx+1]
            hp0=h[h_idx]
            hm1=h[h_idx-1]     
            d=hp0
            c=(hp1-hm1)/2.
            b=(-hp2+4*hp1-5*hp0+2*hm1)/2.
            a=(hp2-3*hp1+3*hp0-hm1)/2.
            xi=(x2_idx - h_idx)
            yout[xdet_idx]=((a * xi + b) * xi + c) * xi + d
            
        return np.array(yout)          
    return func(x2)


def interpol(signal, x, extrapolate=False):
    """
    Linear interpolation of array signal at floating point indices x
    (x can be an array or a scalar). If x is beyond range either the first or
    last element is returned. If extrapolate=True, the linear extrapolation of
    the first/last two points is returned instead.
    """
    n = np.alen(signal)
    if n == 1:
        return signal[0]
    i = np.floor(x).astype(int)
    i = np.clip(i, 0, n-2) #assumes x is between 0 and n-1
    p = x - i
    if not extrapolate:
        p = np.clip(p,0.0,1.0)
    return signal[i] * (1.0 - p) + signal[i+1] * p


def findRelevant(starts, ends):
    n = np.size(starts)
    relevant = np.resize(True, n)
    for i in np.arange(n-1):
        relevant[i] = not np.any((starts[i+1:] <= starts[i]) &
                                    (ends[i+1:] >= ends[i]))
    return np.argwhere(relevant)[:,0]


##################################################
#                                                #
# Correction class for a DAC board with IQ mixer #
#                                                #
##################################################


class IQcorrection:

    def __init__(self, board, lowpass=cosinefilter, bandwidth=0.4,
                 exceedCalLimits=0.001):

        """
        Returns a DACcorrection object for the given DAC board.
        """

        self.board = board
        #Set dynamic reserve
        self.dynamicReserve = 2.0

        #Use this to see how much the last DACify call rescaled the output
        self.last_rescale_factor = 1.0
        #Use this to see the smallest rescale factor DACify had to use
        self.min_rescale_factor = 1.0

        self.flipChannels = False

        # Set the Lowpass, i.e. the transfer function we want after correction
        # Unless otherwise specified, the filter will be flat and then roll off
        # between (1-bandwidth)*Nyquist and Nyquist

        if lowpass == False:
            lowpass = flatfilter

        self.lowpass = lowpass
        self.bandwidth = bandwidth
        self.exceedCalLimits = exceedCalLimits

        # empty pulse calibration
        self.correctionI = None
        self.correctionQ = None
        self.pulseCalFile = None

        # empty zero calibration
        self.zeroTableStart = np.zeros(0,dtype=float)
        self.zeroTableEnd = np.zeros(0,dtype=float)
        self.zeroTableStep = np.zeros(0,dtype=float)
        self.zeroCalFiles = np.zeros(0,dtype=int)
        self.zeroTableI = []
        self.zeroTableQ = []

        # empty sideband calibration
        self.sidebandCarrierStart = np.zeros(0,dtype=float)
        self.sidebandCarrierEnd = np.zeros(0,dtype=float)
        self.sidebandCarrierStep = np.zeros(0,dtype=float)
        self.sidebandStep = np.zeros(0,dtype=float)
        self.sidebandCount = np.zeros(0)
        self.sidebandCompensation = []
        self.sidebandCalFiles = np.zeros(0,dtype=int)

        self.selectCalAll()
        
        self.recalibrationRoutine = None


    def loadZeroCal(self, zeroData, calfile):
        l = np.shape(zeroData)[0]
        self.zeroTableI.append(zeroData[:,(1 + self.flipChannels)])
        self.zeroTableQ.append(zeroData[:,(1 + (not self.flipChannels))])
        self.zeroTableStart = np.append(self.zeroTableStart, zeroData[0,0])
        self.zeroTableEnd = np.append(self.zeroTableEnd, zeroData[-1,0])
        self.zeroCalFiles = np.append(self.zeroCalFiles, calfile)
        if l > 1:
            self.zeroTableStep = np.append(self.zeroTableStep,
                                              zeroData[1,0]-zeroData[0,0])
            print '  carrier frequencies: %g GHz to %g GHz in steps of %g MHz' % \
                (zeroData[0,0], zeroData[-1,0],
                self.zeroTableStep[-1]*1000.0)

        else:
            self.zeroTableStep = np.append(self.zeroTableStep, 1.0)
            print '  carrier frequency: %g GHz' % zeroData[0,0]


    def eliminateZeroCals(self):
        """
        Eliminate zero calibrations that have become obsolete.
        Returns the zero calibration files that are still used.
        You should not need to call this function. It is used internally
        during a recalibration.
        """
        keep = findRelevant(self.zeroTableStart,self.zeroTableEnd)
        self.zeroTableI = [self.zeroTableI[i] for i in keep]
        self.zeroTableQ = [self.zeroTableQ[i] for i in keep]
        self.zeroTableStart = self.zeroTableStart[keep]
        self.zeroTableEnd = self.zeroTableEnd[keep]
        self.zeroTableStep = self.zeroTableStep[keep]
        self.zeroCalFiles = self.zeroCalFiles[keep]
        return self.zeroCalFiles


    def loadSidebandCal(self, sidebandData, sidebandStep, calfile):
        """
        Load IQ sideband mixing calibration
        """
        self.sidebandStep = np.append(self.sidebandStep, sidebandStep)
        
        l,sidebandCount = np.shape(sidebandData)
        sidebandCount = (sidebandCount-1)/2

        self.sidebandCarrierStart = np.append(self.sidebandCarrierStart,
                                           sidebandData[0,0])
        self.sidebandCarrierEnd = np.append(self.sidebandCarrierEnd,
                                         sidebandData[-1,0])
        if l>1:
            self.sidebandCarrierStep = np.append(self.sidebandCarrierStep, 
                sidebandData[1,0] - sidebandData[0,0])
            print '  carrier frequencies: %g GHz to %g GHz in steps of %g MHz' % \
                  (sidebandData[0,0],
                   sidebandData[-1,0],
                   self.sidebandCarrierStep[-1]*1000.0)
        else:
            self.sidebandCarrierStep = np.append(self.sidebandCarrierStep,
                                                    1.0)
            print '  carrier frequency: %g GHz' % sidebandData[0,0]

        sidebandData = np.reshape(sidebandData[:,1:],(l,sidebandCount, 2))
        self.sidebandCompensation.append(
            sidebandData[:,:,0] + 1.0j * sidebandData[:,:,1])
        self.sidebandCalFiles = np.append(self.sidebandCalFiles, calfile)
        print '  sideband frequencies: %g MHz to %g Mhz in steps of %g MHz' % \
              (-500.0*(sidebandCount-1)*sidebandStep,
               500.0*(sidebandCount-1)*sidebandStep,
               sidebandStep*1000)

        
    def eliminateSidebandCals(self):
        """
        Eliminate sideband calibrations that have become obsolete.
        Returns the sideband calibration files that are still used.
        You should not need to call this function. It is used internally
        during a recalibration.
        """
        keep = findRelevant(self.sidebandCarrierStart,self.sidebandCarrierEnd)
        self.sidebandCompensation = [self.sidebandCompensation[i] for i in keep]
        self.sidebandStep = self.sidebandStep[keep]
        self.sidebandCarrierStart = self.sidebandCarrierStart[keep]
        self.sidebandCarrierEnd = self.sidebandCarrierEnd[keep]
        self.sidebandCarrierStep = self.sidebandCarrierStep[keep]
        self.sidebandCalFiles = self.sidebandCalFiles[keep]
        return self.sidebandCalFiles
        

    def loadPulseCal(self, dataPoints, carrierfreq, calfile,
                     flipChannels = False):
        """
        Demodulates the IQ mixer output with the carrier frequency.
        The result is inverted and multiplied with a lowpass filter, that rolls
        off between 0.5-cufoffwidth GHz and 0.5 GHz.
        It is stored in self.correctionI and self.correctionQ.
        """
        #read pulse calibration from data server
        self.flipChannels = flipChannels
        dataPoints = np.asarray(dataPoints)
        i = dataPoints[:,1 + self.flipChannels]
        q = dataPoints[:,1 + (not self.flipChannels)]
        # subtract DC offsets
        i -= np.average(i)
        q -= np.average(q)
        length = len(i)
        samplingfreq = int(np.round(1.0/(dataPoints[1,0]-dataPoints[0,0])))
        dataPoints = None

        #length for fft, long because we want good frequency resolution
        finalLength = 10240
        n = finalLength*samplingfreq
        print '  sampling frequency: %d GHz' % samplingfreq

        #convert carrier frequency to index
        carrierfreqIndex = carrierfreq*n/samplingfreq

        #if the carrier frequency doesn't fall on a frequency sampling point
        #we lose some precision
        if np.floor(carrierfreqIndex) < np.ceil(carrierfreqIndex):
            print """Warning: carrier frequency of calibration is not a multiple of %g MHz, accuracy may suffer.""" % 1000.0*samplingfreq/n
        carrierfreqIndex = int(np.round(carrierfreqIndex))

        #go to frequency space
        i = np.fft.rfft(i, n=n)
        q = np.fft.rfft(q, n=n)

        #demodulate
        low = i[carrierfreqIndex:carrierfreqIndex-finalLength/2-1:-1]
        high = i[carrierfreqIndex:carrierfreqIndex+finalLength/2+1:1]
        #calcualte the phase of the carrier
        phase = np.sqrt(np.sum(low*high))
        phase /= abs(phase)
        if (phase.conjugate()*low[0]).real < 0:
            phase *= -1

        self.correctionI = 1.0 / \
            (0.5 / abs(low[0]) * (np.conjugate(low/phase) + high/phase))

        low = q[carrierfreqIndex:carrierfreqIndex-finalLength/2-1:-1]
        high = q[carrierfreqIndex:carrierfreqIndex+finalLength/2+1:1]
        #calculate the phase of the carrier
        phase = np.sqrt(np.sum(low*high))
        phase /= abs(phase)
        if (phase.conjugate()*low[0]).real < 0:
            phase *= -1
        self.correctionQ = 1.0 / \
            (0.5 / abs(low[0]) * (np.conjugate(low/phase) + high/phase))
        #Make sure the correction does not get too large
        #If correction goes above 3 * dynamicReserve,
        #scale to 3 * dynamicReserve but preserve phase
        self.correctionI /= \
            np.clip(abs(self.correctionI) / 3. / self.dynamicReserve,
                       1.0, np.Inf)
        self.correctionQ /= \
            np.clip(abs(self.correctionQ) / 3. /self.dynamicReserve,
                       1.0, np.Inf)
        self.pulseCalFile = calfile


    def selectCalAll(self):
        """
        For each frequency use the lastest calibration available. This
        is the default behaviour.
        """
        self.zeroCalIndex = None
        self.sidebandCalIndex = None
        print 'For each correction the best calfile will be chosen.'


    def selectCalLatest(self):
        """
        Only use the latest calibration and extrapolate it if the
        carrier frequency lies outside the calibrated range
        """

        self.zeroCalIndex = -1
        self.sidebandCalIndex = -1
        print 'Zero     calibration:  selecting calset %d' % \
            self.zeroCalFiles[-1]
        print 'Sideband calibration:  selecting calset %d' % \
            self.sidebandCalFiles[-1]


    def findCalset(self, rangeStart, rangeEnd, calStarts, calEnds, calType):
        
        badness = np.max([np.resize(self.exceedCalLimits,
                                          np.shape(calStarts)),
                             calStarts-rangeStart,
                             rangeEnd-calEnds], axis=0)
        i = np.size(badness) - np.argmin(badness[::-1]) - 1
        if badness[i] > self.exceedCalLimits:
            print '\n  closest calset: %g, only covers %g GHz to %g GHz' \
                  % (i,calStarts[i], calEnds[i])
        return i


    def selectCalByRange(self, start,end):
        """
        Use only the latest calibration covering the given range. If
        there is no such calibration use the one that is closest to
        covering it.
        """
        print 'Zero     calibration:',        
        self.zeroCalIndex = self.findCalset(start, end, self.zeroTableStart,
                                       self.zeroTableEnd, 'zero')
        print '  selecting calset %d' % \
              self.zeroCalFiles[self.zeroCalIndex]
        print 'Sideband calibration:', 
        self.sidebandCalIndex = self.findCalset(start, end,
                                                self.sidebandCarrierStart,
                                                self.sidebandCarrierEnd,
                                                'sideband')
        print '  selecting calset %d' % \
              self.sidebandCalFiles[self.sidebandCalIndex]

    def DACzeros(self, carrierFreq):
        """
        Returns the DAC values for which, at the given carrier
        frequency, the IQmixer output power is smallest.
        Uses cubic interpolation
        """
        if self.zeroTableI == []:
            return [0.0,0.0]
        i = self.zeroCalIndex
        if i is None:
            i = self.findCalset(carrierFreq, carrierFreq, self.zeroTableStart,
                                self.zeroTableEnd, 'zero')
        carrierFreqFreq=carrierFreq
        carrierFreq = (carrierFreq - self.zeroTableStart[i]) / self.zeroTableStep[i]  #now it becomes and index
        #zeroI=interpol_cubic(self.zeroTableI[i], carrierFreq)
        #zeroQ=interpol_cubic(self.zeroTableQ[i], carrierFreq)
        #print 'board:',self.board,'  freq:',carrierFreqFreq,'  zeroI,Q:',zeroI,zeroQ
        return [interpol_cubic(self.zeroTableI[i], carrierFreq), interpol_cubic(self.zeroTableQ[i], carrierFreq)]
        #return [interpol(self.zeroTableI[i], carrierFreq), interpol(self.zeroTableQ[i], carrierFreq)] #old
                
    def _IQcompensation(self, carrierFreq, n):
        """
        Returns the sideband correction at the given carrierFreq and for
        sideband frequencies
        (0, 1, 2, ..., n/2, n/2+1-n, ..., -1, 0) * (1.0 / n) GHz
        """
        if self.sidebandCompensation == []:
            return np.zeros(n+1, dtype = complex)
        i = self.sidebandCalIndex
        if i is None:
            i = self.findCalset(carrierFreq, carrierFreq, 
                           self.sidebandCarrierStart,
                           self.sidebandCarrierEnd, 'sideband')
        carrierFreq = (carrierFreq - self.sidebandCarrierStart[i]) / \
            self.sidebandCarrierStep[i]
        w = np.shape(self.sidebandCompensation[i])[1]
        maxfreq = 0.5 * self.sidebandStep[i] * (w-1)
        p = self.sidebandStep[i]/(1-2*maxfreq)
        freqs = np.zeros(n+1,dtype=float)
        freqs[1:n/2+1] = np.arange(1,n/2+1)
        freqs[n/2+1:n] = np.arange(n/2+1-n,0)
        freqs /= n
        compensation = np.zeros(w+2,complex)
        compensation[1:w+1] = interpol(self.sidebandCompensation[i],carrierFreq)
        compensation[0]   = (1 - p) * compensation[1] + p * compensation[w]
        compensation[w+1] = (1 - p) * compensation[w] + p * compensation[1]
        return interpol(compensation,
            (freqs + maxfreq + self.sidebandStep[i]) / self.sidebandStep[i],
            extrapolate=True)


    def DACify(self, carrierFreq, i, q=None, loop=False, rescale=False,
               zerocor=True, deconv=True, iqcor=True, zipSRAM=True,
               zeroEnds=False):
        """
        Computes a SRAM sequence from I and Q values in the range from
        -1 to 1.  If Q is omitted, the imaginary part of I sets the Q
        value

        Perfroms the following corrections at the given carrier frequency
        (in GHz):
            - DAC zeros
            - deconvolution with filter chain response
              (For length-1 i and q, this correction cannot be performed)
            - IQ mixer

        DACify only sets the lowest 28 bits of the SRAM samples.  Add
        trigger signals to the highest 4 bits via bitwise or when
        needed.

        If you use deconvolution and unless you have a periodic signal
        (i.e. the signal given to DACify is looped without any dead
        time), you should have at least 5ns before and 20ns after your
        pulse where the signal is 0 (or very small). Otherwise your
        signal will be deformed because the correction for the DAC
        pulse response will either be clipped or wrapped around and
        appear at the beginning of your signal!

        Keyword arguments:

        loop=True: Does the the FFT on exactly the length of i and q.
            You need this if you have a periodic signal that is
            non-zero at the borders of the signal (like a continous
            sinewave). Otherwise DACify could do the fft on a larger
            array (padded with 0) in order to have a faster fft (fft
            is fastest for numbers that factorize into small numbers)

        rescale=True: If the corrected signal exceeds the DAC range,
            it is rescaled to fit. Useful to drive as hard as possible
            without signal distortions (e.g. for spectroscopy).
            Otherwise the signal is clipped. After a DACify call
            DACcorrection.last_rescale_factor contains the rescale
            factor actually used. DACcorrection.min_rescale_factor
            contains the smallest rescale factor used so far.

        zerocor=False: Do not perform zero correction.

        deconv=False: Do not perform deconvolution. Sideband frequency
            dependence of the IQ compensation will be ignored.

        iqcor=False: Do not perform IQ mixer correction.

        zipSRAM=False: returns (I,Q) tuples instead of packed SRAM data,
            tuples are not clipped to fit the DAC range.

        Example:
            cor = DACcorrection('DR Lab FPGA 0')
            t = arange(-50.0,50.0)
            # 5 ns FWHM Gaussian at 6 GHz carrier frequency,
            # sideband mixed to 6.1 GHz
            signal=2.0**(-t**2/2.5**2) * exp(-2.0j*pi*0.1*t)
            signal = cor.DACify(6.0, signal)
            #add trigger
            signal[0] |= 0xF<<28
            fpga.loop_sram(signal)
        """
        i = np.asarray(i)
        if q == None:
            i = i.astype(complex)
        else:
            i = i + 1.0j * q
        n = np.alen(i)
        if loop:
            nfft = n
        else:
            nfft = fastfftlen(n)
        if n > 1:
            # treat offset properly even when n != nfft
            background = 0.5*(i[0]+i[-1])
            i = np.fft.fft(i-background,n=nfft)
            i[0] += background * nfft
        return self.DACifyFT(carrierFreq, i, n=n, loop=loop, rescale=rescale,
               zerocor=zerocor, deconv=deconv, iqcor=iqcor, zipSRAM=zipSRAM,
               zeroEnds=zeroEnds)

    
    def DACifyFT(self, carrierFreq, signal, t0=0, n=8192, loop=False,
                 rescale=False, zerocor=True, deconv=True, iqcor=True,
                 zipSRAM=True, zeroEnds=False):
        """
        Works like DACify but takes the Fourier transform of the
        signal as input instead of the signal itself. Because of that
        DACifyFT is faster and more acurate than DACify and you do not
        have to lowpass filter the signal before sampling it.
        n gives the number of points (or the length in ns),
        t0 the start time.  Signal can either be a function which will
        be evaluated between -0.5 and 0.5 GHz, or an array of length
        nfft with complex samples at frequencies in GHz of
           np.linspace(0.5, 1.5, nfft, endpoint=False) % 1 - 0.5
        If you want DACifyFT to be fast nfft should factorize in 2 3 and 5.
        If n < nfft, the result is truncated to n samples.
        For the rest of the arguments see DACify.
        """
        if n == 0:
            return np.zeros(0)
        if callable(signal):
            if loop:
                nfft = n
            else:
                nfft = fastfftlen(n)
        elif signal is None:
            if zerocor:
                i,q = self.DACzeros(carrierFreq)
                signal = np.uint32((int(np.round(i)) & 0x3FFF) \
                                << (14 * self.flipChannels) | \
                                (int(np.round(q)) & 0x3FFF) \
                                << (14 * (not self.flipChannels)))
            else:
                signal = np.uint32(0)
            return np.resize(signal, n)
        else:
            signal = np.asarray(signal)
            nfft = np.alen(signal)
        if n > nfft:
            n = nfft
        nrfft = nfft/2+1
        f = np.linspace(0.5, 1.5, nfft, endpoint=False) % 1 - 0.5
        if callable(signal):
            signal = np.asarray(signal(f)).astype(complex)
        if t0 != 0:
            signal *= np.exp(2.0j*np.pi*t0*f)
        
        if n > 1:
            #apply convolution and iq correction
            #FT the input
            #add the first point at the end so that the elements of signal and
            #signal[::-1] are the Fourier components at opposite frequencies
            signal = np.hstack((signal, signal[0]))

            #correct for the non-orthoganality of the IQ channels
            if iqcor:
                signal += signal[::-1].conjugate() * \
                          self._IQcompensation(carrierFreq, nfft)
            

            #separate I (FT of a real signal) and Q (FT of an imaginary signal)
            i =  0.5  * (signal[0:nrfft] + \
                             signal[nfft:nfft-nrfft:-1].conjugate())
            q = -0.5j * (signal[0:nrfft] - \
                             signal[nfft:nfft-nrfft:-1].conjugate())

            #resample the FT of the response function at intervals 1 ns / nfft
            if deconv and (self.correctionI != None):
                l = np.alen(self.correctionI)
                freqs = np.arange(0,nrfft) * 2.0 * (l - 1.0) / nfft
                #correctionI = interpol(self.correctionI, freqs,extrapolate=True)
                #correctionQ = interpol(self.correctionQ, freqs,extrapolate=True)
                correctionI = interpol_cubic(self.correctionI, freqs, fill_value=0.0)
                correctionQ = interpol_cubic(self.correctionQ, freqs, fill_value=0.0)                
                lp = self.lowpass(nfft, self.bandwidth)
                i *= correctionI * lp
                q *= correctionQ * lp
            #do the actual deconvolution and transform back to time space
            i = np.fft.irfft(i, n=nfft)[:n]
            q = np.fft.irfft(q, n=nfft)[:n]
        else:
            #only apply iq correction for sideband frequency 0
            if iqcor:
                signal += signal.conjugate() * \
                    self._IQcompensation(carrierFreq,1)[0]
            i = signal.real
            q = signal.imag
            
        # rescale or clip data to fit the DAC range
        fullscale = 0x1FFF / self.dynamicReserve

        if zerocor:
            zeroI, zeroQ = self.DACzeros(carrierFreq)
        else:
            zeroI = zeroQ = 0.0
        
        if rescale:
            rescale = np.min([1.0,
                           ( 0x1FFF - zeroI) / fullscale / np.max(i),
                           (-0x2000 - zeroI) / fullscale / np.min(i),
                           ( 0x1FFF - zeroQ) / fullscale / np.max(q),
                           (-0x2000 - zeroQ) / fullscale / np.min(q)])
            if rescale < 1.0:
                print 'Corrected signal scaled by %g to fit DAC range.' % \
                    rescale
            # keep track of rescaling in the object data
            self.last_rescale_factor = rescale
            if not isinstance(self.min_rescale_factor, float) \
               or rescale < self.min_rescale_factor:
                self.min_rescale_factor = rescale
            fullscale *= rescale

        # Due to deconvolution, the signal to put in the dacs can be nonzero at
        # the end of a sequence even with a short pulse. This nonzero value
        # exists even when running the board with an empty envelope. To remove
        # it, the first and last 4 (FOUR) values must be set to zero.
        if zeroEnds:
            i[:4] = 0.0
            i[-4:] = 0.0
            q[:4] = 0.0
            q[-4:] = 0.0
        i = np.round(i * fullscale + zeroI).astype(np.int32)
        q = np.round(q * fullscale + zeroQ).astype(np.int32)
        


        if not rescale:
            clippedI = np.clip(i,-0x2000,0x1FFF)
            clippedQ = np.clip(q,-0x2000,0x1FFF)
            if np.any((clippedI != i) | (clippedQ != q)):
                print 'Corrected IQ signal beyond DAC range, clipping'
            i = clippedI
            q = clippedQ
            
        if not zipSRAM:
            return (i, q)

        return ((i & 0x3FFF) << (14 * self.flipChannels) | \
                (q & 0x3FFF) << (14 * (not self.flipChannels))).\
                astype(np.uint32)


    def recalibrate(self, carrierMin, carrierMax=None, zeroCarrierStep=0.02,sidebandCarrierStep=0.05, sidebandMax=0.35, sidebandStep=0.05):
        if carrierMax is None:
                carrierMax = carrierMin
        if self.recalibrationRoutine is None:
            print 'No calibration routine hooked in.'
            return self
        return self.recalibrationRoutine(self.board, carrierMin, carrierMax,
                                         zeroCarrierStep, sidebandCarrierStep,
                                         sidebandMax, sidebandStep, self)
 


#############################################
#                                           #
# Correction class for a single DAC channel #
#                                           #
#############################################



class DACcorrection:


    def __init__(self, board, channel, lowpass=gaussfilter, bandwidth=0.15):

        """
        Returns a DACcorrection object for the given DAC board.
        keywords:
       
            lowpass: Sets the low pass filter function,
                i.e. the transfer function we want after
                correction. It expects func of form func(n,
                bandwidth). n is the number of samples between 0
                frequency and the Nyquist frequency (half the sample
                freq).  bandwidth is all the other parameters the
                function needs, they are passed to func just as
                specified by the bandwidth keyword to
                DACcorrection. The return value is the transmission
                (between 0 and 1) at f=0, 1/N, ... (n-1)/N where N is
                the Nyquist frequency.  Default: gaussfilter
                
            bandwidth: bandwidth are arguments passed to the lowpass
                filter function (see above)
             
            RB: This filter setting is controlled in the __init__.py, not here

        """

        self.board = board
        self.channel = channel
        #Set dynamic reserve
        self.dynamicReserve = 2.0

        #Use this to see how much the last DACify call rescaled the output
        self.last_rescale_factor = 1.0
        #Use this to see the smallest rescale factor DACify had to use
        self.min_rescale_factor = 1.0

        # Set the Lowpass, i.e. the transfer function we want after correction
        if lowpass == False:
            lowpass = flatfilter
        self.lowpass = lowpass
        self.bandwidth = bandwidth
        print lowpass.__name__ , bandwidth
        self.correction = []

        self.zero = 0.0

        self.clicsPerVolt = None

        self.decayRates = np.array([])
        self.decayAmplitudes = np.array([])
        self.reflectionRates = np.array([])
        self.reflectionAmplitudes = np.array([])        
        self.precalc = np.array([])



    def loadCal(self, dataPoints, zero=0.0 , clicsPerVolt=None,
                lowpass=flatfilter, bandwidth=0.15, replace=False,maxfreqZ=0.45):
        """
        Adds a response function to the list of internal
        calibrations. dataPoints contains a step response. It is a n x
        2 array. dataPoints[:,0] contains the time in dacIntervals,
        dataPoints[:,1] the amplitude (scale does not matter).

        If you add a SECONDARY CALIBRATION (i.e. a calibration that
        has been obtained with a input signal already numerically
        corrected) then you have to PROVIDE THE OPTIONAL 'lowpass'
        and 'bandwidth' ARGUMENTS to tell the deconvolution
        about the numerical lowpass filter you used to generate the
        input signal for the calibration. If you omit these
        parameters, DACify will also correct for the numerical lowpass
        filter: If you use the same numerical lowpass filter to
        generate the calibration and when you call DACify, they will
        cancel and you get no lowpass filter; If you use a narrower
        filter to generate the calibration than when you call DACify,
        you will end up with a band pass, certainly not what you want.

        The optional 'zero' argument gives the DAC value, giving 0 output,
        defaults to 0.
        
        maxfreqZ=0.45 is optimal (10% below Nyquist frequency)
        """

        #read pulse calibration from data server
        samplingfreq = int(np.round(1.0/(dataPoints[1,0]-dataPoints[0,0])))
        samplingtime = dataPoints[:,0]
        stepResponse = dataPoints[:,1]
        
        #standard way of generating the impulse response function:
        #apply moving average filter
        #stepResponse = moving_average(stepResponse,np.round(samplingfreq/2.5)) 
        #The moving average filter by Max is a bit too much, it leads to visible ringing for short (~20 ns) Z pulse
        #get impulse response from step response
        #Normally: h(t) = d/dt u(t), and:
        #impulseResponse = derivative(samplingtime,stepResponse)
        
        #however, we have spurious 1 GHz, 2 GHz etc signals. We can suppress that by subtracting one point from the other which is 1 ns away. 
        #This also averages over a ns. 
        #If we don't do this, we end up with the amplitude after a Z pulse being dissimilar to the idle amplitude, because of aliasing.
        #One issue is that this amplifies noise at 500 MHz, therefore we HAVE to cut it off later
        distance=samplingfreq
        impulseResponse = stepResponse[distance:]-stepResponse[:-distance]
        samplingtime = samplingtime[0:np.alen(impulseResponse)-1] #+ distance/2.0/samplingfreq
        
        #get time shift from the impulse response
        idx = impulseResponse.argmax()
        tshift = samplingtime[idx]
        
        self.dataPoints = impulseResponse         #THIS CONTAINS THE TIME DOMAIN SIGNAL

        #compute correction to apply in frequency domain
        finalLength = 102400 #length for fft, long because we want good frequency resolution
        n = finalLength*samplingfreq #this is done, so we can later take 0:finalLength/2+1, i.e. 0 to 500 MHz. The progam expects this frequency range, so DON'T change it.
        
        #go to frequency space, and calculate the frequency domain correction function ~1/H
        impulseResponse_FD = np.fft.rfft(impulseResponse,n=n) #THIS CONTAINS THE FREQ DOMAIN SIGNAL    
        freqs=samplingfreq/2.0*np.arange(np.alen(impulseResponse_FD))/np.alen(impulseResponse_FD)
        
        #Normally the deconv corrects for the measured impulse response not appearing at t=0.
        #This is bad, because A) the phase will depend strongly on frequency, which is harder to interpolate and 
        #B) the time domain signal will run out of its memory block.
        #Here we apply a timeshift tshift, so the deconv won't shift the pulse in time.        
        impulseResponse_FD *= np.exp(2.0j*np.pi*freqs*tshift)
        
        #the correction window ~1/H(f)
        correction = lowpass(finalLength,bandwidth) * abs(impulseResponse_FD[0]) / impulseResponse_FD[0:finalLength/2+1] #0:finalLength/2+1 = 0 to 500 MHz. The progam expects this frequency range in other functions, so DON'T change it.

        #apply a cut off frequency, necessary to kick out 500 MHz signal which messes up dualblock scans with nonzero Z. 
        #Also, the 1 GHz suppression applied above amplifies noise at 500 MHz.
        if maxfreqZ:
            freqs=0.5*np.arange(np.alen(correction))/np.alen(correction)        
            correction = correction * 1.0 * (abs(freqs)<=maxfreqZ)
        
        self.correction += [correction]        
        self.zero = zero
        self.clicsPerVolt = clicsPerVolt
        self.precalc = np.array([])
     
        
    def setSettling(self, rates, amplitudes):
        """
        If a calibration can be characterized by time constants, i.e.
        the step response function is
          0                                             for t <  0
          1 + sum(amplitudes[i]*exp(-decayrates[i]*t))  for t >= 0,
        then you don't need to load the response function explicitly
        but can just give the timeconstants and amplitudes.
        All previously used time constants will be replaced.
        """
        rates = np.asarray(rates)
        amplitudes = np.asarray(amplitudes)
        if np.shape(rates) != np.shape(amplitudes):
            raise Error('arguments to setSettling must have same shape.')
        s = np.size(rates)
        rates = np.reshape(np.asarray(rates),s)
        amplitudes = np.reshape(np.asarray(amplitudes),s)
        if (not np.array_equal(self.decayRates,rates)) or (not np.array_equal(self.decayAmplitudes,amplitudes)):
            print 'emptying precalc (settling)'
            self.decayRates = rates
            self.decayAmplitudes = amplitudes
            self.precalc = np.array([])
        
    def setReflection(self, rates, amplitudes):
        """ Correct for reflections in the line.
        Impulse response of a line reflection is H = (1-amplitude) / (1-amplitude * exp( -2i*pi*f/rate) )
        All previously used time constants for the reflections will be replaced.
        """
        rates = np.asarray(rates)
        amplitudes = np.asarray(amplitudes)
        if np.shape(rates) != np.shape(amplitudes):
            raise Error('arguments to setReflection must have same shape.')
        s = np.size(rates)
        rates = np.reshape(np.asarray(rates),s)
        amplitudes = np.reshape(np.asarray(amplitudes),s)
        if (not np.array_equal(self.reflectionRates,rates)) or (not np.array_equal(self.reflectionAmplitudes,amplitudes)):
            print 'emptying precalc (reflection)'
            self.reflectionRates = rates
            self.reflectionAmplitudes = amplitudes
            self.precalc = np.array([])
        
        
    def setFilter(self, lowpass=None, bandwidth=0.15):
        """
        Set the lowpass filter used for deconvolution.
       
        lowpass: Sets the low pass filter function, i.e. the transfer
            function we want after correction. It expects func of form
            func(n, bandwidth). n is the number of samples between 0
            frequency and the Nyquist frequency (half the sample
            freq).  bandwidth is all the other parameters the function
            needs, they are passed to func just as specified by the
            bandwidth keyword to DACcorrection. The return value is
            the transmission (between 0 and 1) at f=0, 1/N,
            ... (n-1)/N where N is the Nyquist frequency.  Default:
            gaussfilter
                
        bandwidth: bandwidth are arguments passed to the lowpass
            filter function (see above)
        """
        if lowpass is None:
            lowpass=self.lowpass
            
        if (self.lowpass != lowpass) or (self.bandwidth != bandwidth):
            self.lowpass = lowpass
            self.bandwidth = bandwidth
            self.precalc = np.array([])


    def DACify(self, signal, loop=False, rescale=False, fitRange=True,
               zerocor=True, deconv=True, volts=True, dither=False,
               averageEnds=False):
        """
        Computes a SRAM sequence for one DAC channel. If volts is
        True, the input is expected in volts. Otherwise inputs of -1
        and 1 correspond to the DAC range divided by
        self.dynamicReserve (default 2). In the latter case, clipping
        may occur beyond -1 and 1.
        DACify corrects for
          - zero offsets (if zerocor is True)
          - gain (if volts is True)
          - pulse shape (if deconv is True)
        DACify returns a long array in the range -0x2000 to 0x1FFF

        If you use deconvolution and unless you have a periodic signal
        (i.e. the signal given to DACify is looped without any dead
        time), you should have at least 5ns before and 200ns (or
        however long the longest pulse calibration trace is) after
        your pulse where the signal is constant with the same value at
        the beginning and the end of the sequence. Otherwise your
        signal will be deformed because the correction for the DAC
        pulse response will either be clipped or wrapped around and
        appear at the beginning of your signal!

        Keyword arguments:

        loop=True: Does the the FFT on exactly the length of the input
            signal.  You need this if you have a periodic signal that
            is non-zero at the borders of the signal (like a continous
            sinewave). Otherwise DACify pads the input with the
            average of the first and the last datapoint to optain a
            signal length for which fft is fast (fft is fastest for
            numbers that factorize into small numbers and extremly
            slow for large prime numbers)

        rescale=True: If the corrected signal exceeds the DAC range,
            it is rescale to fit. Usefull to drive as hard as possible
            without signal distorsions (e.g. for spectroscopy).
            Otherwise the signal is clipped. After a DACify call
            DACcorrection.last_rescale_factor contains the rescale factor
            actually used. DACcorrection.min_rescale_factor contains the
            smallest rescale factor used so far.
            
        fitRange=False: Do not clip data to fit into 14 bits. Only
            effective without rescaling.

        zerocor=False: Do not perform zero correction.

        deconv=False: Do not perform deconvolution.

        volts=False: Do not correct the gain. A input signal of
             amplitude 1 will then result in an output signal with
             amplitude DACrange/dynamicReserve
        """

        signal = np.asarray(signal)

        if np.alen(signal) == 0:
            return np.zeros(0)

        n = np.alen(signal)

        if loop:
            nfft = n
        else:
            nfft = fastfftlen(n)
            
        nrfft = nfft/2+1
        background = 0.5*(signal[0] + signal[-1])
        signal_FD = np.fft.rfft(signal-background, n=nfft) #FT the input
        signal = self.DACifyFT(signal_FD, t0=0, n=n, nfft=nfft, offset=background,
                             loop=loop,
                             rescale=rescale, fitRange=fitRange, deconv=deconv,
                             zerocor=zerocor, volts=volts, dither=dither,
                             averageEnds=averageEnds)
        return signal


    def DACifyFT(self, signal, t0=0, n=8192, offset=0, nfft=None, loop=False,
                 rescale=False, fitRange=True, deconv=True, zerocor=True,
                 volts=True, maxvalueZ=5.0, dither=False, averageEnds=False):
        """
        Works like DACify but takes the Fourier transform of the
        signal as input instead of the signal. n gives the number of
        points (or the length in ns), t0 the start time.  Signal can
        either be an array of length n/2 + 1 giving the frequency
        components from 0 to 500 MHz. or a function which will be
        evaluated between 0 and 0.5 (GHz). For the rest of the
        arguments see DACify
        """

        # TODO: Remove this hack that strips units
        decayRates = np.array([x['GHz'] for x in self.decayRates])
        decayAmplitudes = self.decayAmplitudes

        reflectionRates = np.array([x['GHz'] for x in self.reflectionRates])
        reflectionAmplitudes = self.reflectionAmplitudes        

        #read DAC zeros
        if zerocor:
            zero = self.zero
        else:
            zero = 0
        if volts and self.clicsPerVolt:
            fullscale = 0x1FFF / self.clicsPerVolt
        else:
            fullscale = 0x1FFF / self.dynamicReserve


        #evaluate the Fourier transform 'signal'
        if callable(signal):
            if loop:
                nfft = n
            elif nfft is None:
                nfft = fastfftlen(n)
            nrfft = nfft/2+1
            signal = np.asarray(signal(np.linspace(0.0, float(nrfft)/nfft, 
                nrfft, endpoint=False))).astype(complex)
        elif signal is None:
            signal = np.int32(np.round(fullscale*offset+zero))
            if fitRange:
                signal = np.clip(signal, -0x2000,0x1FFF)
                signal = np.uint32(signal & 0x3FFF)
            return np.resize(signal, n)
        else:
            signal = np.asarray(signal)
            nrfft = len(signal)
            if nfft is None or nfft/2 + 1 != nrfft:
                nfft = 2*(nrfft-1)

            
        if t0 != 0:
            signal *= np.exp(np.linspace(0.0,
                2.0j * np.pi * t0 * nrfft / nfft, nrfft, endpoint=False))
        signal[0] += nfft*offset
        #do the actual deconvolution and transform back to time space
        if deconv:
            # check if the precalculated correction matches the
            # length of the data, if not we have to recalculate        
            if np.alen(self.precalc) != nrfft:
                # lowpass filter
                precalc = self.lowpass(nfft, self.bandwidth).astype(complex)

                freqs = np.linspace(0, nrfft * 1.0 / nfft,
                                           nrfft, endpoint=False)
                i_two_pi_freqs = 2j*np.pi*freqs

                # pulse correction
                for correction in self.correction:
                    l = np.alen(correction)
                    precalc *= interpol_cubic(correction, freqs*2.0*(l-1)) #cubic, as fast as linear interpol
                    
                # Decay times:
                # add to qubit registry the following keys:
                # settlingAmplitudes=[-0.05]  #relative amplitude
                # settlingRates = [0.01 GHz]    #rate is in GHz, (1/ns)
                if np.alen(decayRates):
                    precalc /= (1.0 + np.sum(decayAmplitudes[:, None] * i_two_pi_freqs[None, :] / (i_two_pi_freqs[None, :] + decayRates[:, None]), axis=0))

                # Reflections:
                # add to qubit registry the following keys:
                # reflectionAmplitudes=[0.05]  #relative amplitude
                # reflectionRates = [0.01 GHz]    #rate is in GHz, (1/ns)
                #
                # Reflections are dealt with by modelling a wire with round-trip time 1/rate, 
                # and reflection coefficient amplitude.
                # It's the simplest model which can describe the effect of reflections in wiring 
                # in for example the wiring between the DAC output and fridge ports. Think about echo, 
                # reflections give rise to an endless sum of copies of the original signal with decreasing amplitude:
                # f(t) -> (1-amplitude) Sum_k=0^\infty (amplitude^k f(t-k 1/rate) ).
                #
                # Suppose X is an ideal pulse, H the impulse response of a piece of cable (with reflection, settling etc). 
                # To get X at the end of the cable you need to send Y = X/H.
                # So if you have different impulse responses H1, H2, H3: Y = X / (H1 * H2 * H3)                
                if np.alen(reflectionRates):
                    for rate,amplitude in zip(reflectionRates,reflectionAmplitudes):
                        if abs(rate) > 0.0:
                            precalc /= (1.0 - amplitude) / (1.0-amplitude*np.exp(-i_two_pi_freqs/rate))

                
                # The correction window can have very large amplitudes,
                # therefore the time domain signal can have large oscillations which will be truncated digitally, 
                # leading to deterioration of the waveform. The large amplitudes in the correction window have low S/N ratios.
                # Here, we apply a maximum value, i.e. truncate the value, but keep the phase. 
                # This way we still have a partial correction, within the limits of the boards. 
                # Doing it this way also helps a lot with the waveforms being scalable.
                if maxvalueZ:
                    precalc = precalc * (1.0 * (abs(precalc)<=maxvalueZ)) + np.exp(1j*np.angle(precalc))*maxvalueZ * 1.0 * (abs(precalc) > maxvalueZ)
                
                self.precalc = precalc
            signal *= self.precalc
        else:
            signal *= self.lowpass(nfft, self.bandwidth)
                
        # transform to real space
        signal = np.fft.irfft(signal, n=nfft)
        signal = signal[0:n]
        
        # Due to deconvolution, the signal to put in the dacs can be nonzero at
        # the end of a sequence with even a short pulse. This nonzero value
        # exists even when running the board with an empty envelope. To remove
        # this, the first and last 4 values must be set.
        if averageEnds:
            signal[0:4] = np.mean(signal[0:4])
            signal[-4:] = np.mean(signal[-4:])

        if rescale:
            rescale = np.min([1.0,
                           ( 0x1FFF - zero) / fullscale / np.max(signal),
                           (-0x2000 - zero) / fullscale / np.min(signal)])
            if rescale < 1.0:
                print 'Corrected signal scaled by %g to fit DAC range.' % \
                    rescale
            # keep track of rescaling in the object data
            self.last_rescale_factor = rescale
            if not isinstance(self.min_rescale_factor, float) \
               or rescale < self.min_rescale_factor:
                self.min_rescale_factor = rescale
            fullscale *= rescale
            
        if dither:
            ditheringspan = 2. #a dithering span of 3 goes from -1.5.. 1.5, i.e. 0..3 = 0,1,2,3 = 4 numbers = 2 bits exactly
        else:
            ditheringspan = 0.
        dithering = ditheringspan * (np.random.rand( len(signal ) )-0.5)
        dithering[0:4] = 0.0
        dithering[-4:] = 0.0

        signal = np.round(1.0*signal * fullscale + zero + dithering).astype(np.int32)

        if not rescale:
            if (np.max(signal) > 0x1FFF) or (np.min(signal) < -0x2000):
                print 'Corrected Z signal beyond DAC range, clipping'
                print 'max: ', np.max(signal)  ,'   min: ', np.min(signal)
                signal = np.clip(signal,-0x2000,0x1FFF)
        if not fitRange:
            return signal  #this returns the signal between -8192 .. + 8191
            
        return (signal & 0x3FFF).astype(np.uint32) #this returns the signal between 0 .. 16383.  -1 = 16382. It will lead to errors visible in fpgatest
