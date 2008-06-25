# Copyright (C) 2007, 2008  Max Hofheinz
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
#
# Version 1.1.0
#
# History
#
# 1.1.0   2008/06/17  added recalibrations and possibility to use several
#                     calibration files
# 1.0.0               first stable version




from numpy import conjugate, array, asarray, floor, ceil, round, min, max, \
alen, clip, sqrt, log, arange, linspace, zeros, ones, reshape, outer, \
compress, sum, shape, cos, pi, exp, Inf, size, real, imag, uint32, int32, \
insert, argmin
from numpy.fft import fft, rfft, irfft



def cosinefilter(n, width=0.4):
    """cosinefilter(n,width) cosine lowpass filter
    n samples from 0 to 0.5 GHz
    1 from 0 GHz to width GHz
    rolls of from width GHz to 0.5 GHz like a quater cosine wave"""
    result = ones(n,dtype=float)
    width = int(round((0.5-width)*n*2.0))
    if width > 0:
        result[n-width:] = 0.5+0.5*cos(linspace(0,pi,width,endpoint=False))
    return result



def gaussfilter(n, width=0.13):
    """ lowpassfilter(n,width) gaussian lowpass filter.
    n samples from 0 to 0.5 GHz
    -3dB frequency at width GHz
    """
    x=0.5 / width * sqrt(log(2.0)/2.0)
    gauss=exp(-linspace(0,x,n,endpoint=False)**2)
    x=gauss[n-1]
    gauss -= x
    gauss /= (1.0 - x)
    return gauss

def flatfilter(n, width=0):
    return 1.0


def fastfftlen(n):

    """
    Computes smallest multiple of 2 3 and 5 above n.
    FFT is fastest for sizes that factorize in small numbers.
    """

    logn=log(n)
    n5 = 5L ** arange(long(logn/log(5.) + 1. + 1.e-6))
    n3 = 3L ** arange(long(logn/log(3.) + 1. + 1.e-6))
    n35 = outer(n3, n5).flat
    n35 =compress(n35<=n,n35);
    n235 = ((-log(n35)+logn)/log(2.) + 0.999999).astype(int)
    n235 = n235.astype(int)
    n235 = 2**((-log(n35)+logn)/log(2.) + 0.999999).astype(int) * n35
    return min(n235)



def interpol(signal, x, extrapolate=False):

    """
    Linear interpolation of array signal at floating point indices x
    (x can be an array or a scalar). If x is beyond range either the first or
    last element is returned. If extrapolate=True, the linear extrapolation of
    the first/last two points is returned instead.
    """
    if len(signal) == 1:
        return signal[0]
    i = floor(x).astype(int)
    n = alen(signal)
    i = clip(i, 0, n-2)
    p = x - i
    if not extrapolate:
        p = clip(p,0.0,1.0)
    return signal[i] * (1.0 - p) + signal[i+1] * p


def findRelevent(starts, ends):
    n = size(starts)
    relevant = resize(True, n)
    for i in arange(1,n):
        relevant[i] = any((starts[:i-1] < starts[i]) & (ends[:i-1] > ends[i]))
    return argwhere(relevant)[:,0]

        
        




##################################################
#                                                #
# Correction class for a DAC board with IQ mixer #
#                                                #
##################################################



class IQcorrection:

    def __init__(self, board, lowpass = cosinefilter, bandwidth = 0.4):

        """
        Returns a DACcorrection object for the given DAC board.
        """

        self.board = board
        #Set dynamic reserve
        self.dynamicReserve=2.0

        #Use this to see how much the last DACify call rescaled the output
        self.last_rescale_factor = 1.0
        #Use this to see the smallest rescale factor DACify had to use
        self.min_rescale_factor = 1.0

        self.flipChannels = False

        # Set the Lowpass, i.e. the transfer function we want after correction
        # Unless otherwise specified, the filter will be flat and than roll off
        # between (1-bandwidth)*Nyquist and Nyquist

        if lowpass == False:
            lowpass = flatfilter

        self.lowpass = lowpass
        self.bandwidth = bandwidth

        # empty pulse calibration
        self.correctionI=None
        self.correctionQ=None
        self.pulseCalFile=None

        # empty zero calibration
        self.zeroTableStart = zeros(0,dtype=float)
        self.zeroTableEnd = zeros(0,dtype=float)
        self.zeroTableStep = zeros(0,dtype=float)
        self.zeroCalFiles = zeros(0)
        self.zeroTableI = []
        self.zeroTableQ = []

        # empty sideband calibration
        self.sidebandCarrierStart = zeros(0,dtype=float)
        self.sidebandCarrierEnd = zeros(0,dtype=float)
        self.sidebandCarrierStep = zeros(0,dtype=float)
        self.sidebandStep = zeros(0,dtype=float)
        self.sidebandCount = zeros(0)
        self.sidebandCompensation = []
        self.sidebandCalFiles = zeros(0)

        self.selectCalAll()
        
        self.recalibrationRoutine=None

    def loadZeroCal(self, zeroData, calfile, position=None):
        if position is None:
            position = size(self.zeroTableStart)

        self.zeroTableI.insert(position,
                               zeroData[:, (1 + self.flipChannels)])
        self.zeroTableQ.insert(position,
                               zeroData[:, (1 + (not self.flipChannels))])
        self.zeroTableStart=insert(self.zeroTableStart, position,
                                   zeroData[0,0])
        self.zeroTableEnd=insert(self.zeroTableEnd, position,
                                 zeroData[-1,0])
        self.zeroTableStep=insert(self.zeroTableStep, position,
                                  zeroData[1,0]-zeroData[0,0])
        self.zeroCalFiles = insert(self.zeroCalFiles, position, calfile)
        print '  carrier frequencies: %g GHz to %g GHz in steps of %g MHz' % \
              (zeroData[0,0], zeroData[-1,0],
               self.zeroTableStep[position]*1000.0)

    def eliminateZeroCals(self):
        """
        Eliminate zero calibrations that have become obsolete.
        Returns the zero calibration files that are still used.
        You should not need to call this function. It is used internally
        during a recalibration.
        """
        keep = findRelevant(self.zeroTableStart,self.zeroTableEnd)
        self.zeroTableI = self.zeroTableI[keep]
        self.zeroTableQ = self.zeroTableQ[keep]
        self.zeroTableStart = self.zeroTableStart[keep]
        self.zeroTableEnd = self.zeroTableEnd[keep]
        self.zeroTableStep = self.zeroTableStep[keep]
        self.zeroCalFiles = self.zeroCalFiles[keep]
        return self.zeroCalFiles


    def loadSidebandCal(self, sidebandData, sidebandStep, calfile, position=None):
        
        """
        Load IQ sideband mixing calibration
        """
        if position is None:
            position = size(self.sidebandCarrierStart)
        
        self.sidebandStep = insert(self.sidebandStep, position, sidebandStep)
        
        l,sidebandCount = shape(sidebandData)
        sidebandCount = (sidebandCount-1)/2

        self.sidebandCarrierStart = insert(self.sidebandCarrierStart,
                                           position, sidebandData[0,0])
        self.sidebandCarrierEnd = insert(self.sidebandCarrierEnd,
                                           position, sidebandData[-1,0])
        self.sidebandCarrierStep = insert(self.sidebandCarrierStep, position, \
            (sidebandData[-1,0] - sidebandData[0,0]) / (l - 1))
        print '  carrier frequencies: %g GHz to %g GHz in steps of %g MHz' % \
              (sidebandData[0,0],
               sidebandData[-1,0],
               self.sidebandCarrierStep[position]*1000.0)
        sidebandData = reshape(sidebandData[:,1:],(l,sidebandCount, 2))
        self.sidebandCompensation.insert(position,
            sidebandData[:,:,0] + 1.0j * sidebandData[:,:,1])
        self.sidebandCalFiles = insert(self.sidebandCalFiles, position, calfile)
        print '  sideband frequencies: %g MHz to %g Mhz in steps of %g MHz' % \
              (-500.0*(sidebandCount-1)*self.sidebandStep,
               500.0*(sidebandCount-1)*self.sidebandStep,
               self.sidebandStep*1000)

        
    def eliminateSidebandCals(self):
        """
        Eliminate sideband calibrations that have become obsolete.
        Returns the zero calibration files that are still used.
        You should not need to call this function. It is used internally
        during a recalibration.
        """
        keep = findRelevant(self.sidebandCarrierStart,self.sidebandCarrierEnd)
        self.sidebandCompensation = self.sidebandCompensation[keep]
        self.sidebandStep = self.sidebandStep[keep]
        self.sidebandCarrierStart = self.sidebandCarrierStart[keep]
        self.sidebandCarrierEnd = self.sidebandCarrierEnd[keep]
        self.sidebandCarrierStep = self.sidebandCarrierStep[keep]
        self.sidebandCalFiles = self.sidebandCalFiles[keep]
        return self.sidebandCalFiles



        

    def loadPulseCal(self, dataPoints, carrierfreq, flipChannels = False):

        """
        Demodulates the IQ mixer output with the carrier frequency.
        The result is inverted and multiplied with a lowpass filter, that rolls
        off between 0.5-cufoffwidth GHz and 0.5 GHz.
        It is stored in self.correctionI and self.correctionQ.
        """

        #read pulse calibration from data server
        self.flipChannels = flipChannels
        dataPoints = asarray(dataPoints)
        i=dataPoints[:,1 + self.flipChannels]
        q=dataPoints[:,1 + (not self.flipChannels)]
        length=len(i)
        samplingfreq=int(round(1.0/(dataPoints[1,0]-dataPoints[0,0])))
        dataPoints=None

        #length for fft, long because we want good frequency resolution
        finalLength=10240
        n=finalLength*samplingfreq
        print '  sampling frequency: %d GHz' % samplingfreq

        #convert carrier frequency to index
        carrierfreqIndex=carrierfreq*n/samplingfreq

        #if the carrier frequecy doesn't fall on a frequecy sampling point
        #we lose some precision
        if floor(carrierfreqIndex) < ceil(carrierfreqIndex):
            print """Warning: carrier frequency of calibration is not
a multiple of %g MHz, accuracy may suffer.""" % 1000.0*samplingfreq/n
        carrierfreqIndex=int(round(carrierfreqIndex))

        #go to frequency space
        i=rfft(i,n=n)
        q=rfft(q,n=n)

        #demodulate
        low = i[carrierfreqIndex:carrierfreqIndex-finalLength/2-1:-1]
        high = i[carrierfreqIndex:carrierfreqIndex+finalLength/2+1:1]
        #calcualte the phase of the carrier
        phase=sqrt(sum(low*high))
        phase/=abs(phase)
        if (conjugate(phase)*low[0]).real < 0:
            phase*=-1

        self.correctionI = 1.0 / \
            (0.5 / abs(low[0]) * (conjugate(low/phase) + high/phase))

        low = q[carrierfreqIndex:carrierfreqIndex-finalLength/2-1:-1]
        high = q[carrierfreqIndex:carrierfreqIndex+finalLength/2+1:1]
        #calcualte the phase of the carrier
        phase=sqrt(sum(low*high))
        phase/=abs(phase)
        if (conjugate(phase)*low[0]).real < 0:
            phase*=-1
        self.correctionQ = 1.0 / \
            (0.5 / abs(low[0]) * (conjugate(low/phase) + high/phase))
        #Make sure the correction does not get too large
        #If correction goes above 3 * dynamicReserve,
        #scale to 3 * dynamicReserve but preserve phase
        self.correctionI /= \
            clip(abs(self.correctionI)/3/self.dynamicReserve, 1.0, Inf)
        self.correctionQ /= \
            clip(abs(self.correctionQ)/3/self.dynamicReserve, 1.0, Inf)


    def selectCalAll(self):
        """For each frequency use the lastest calibration available. This is the default behaviour.""" 
        self.zeroCalIndex = None
        self.sidebandCalIndex = None

    def selectCalLatest(self):
        """Only use the latest calibration and extrapolate it if the carrier frequency lies outside the calibrated range"""
        self.zeroCalIndex = 0
        self.sidebandCalIndex = 0

    def selectCalByRange(self, start,end):
        """Use only the latest calibration covering the given range. If there is no such calibration use the one that is closest to covering it."""
        
        self.zeroCalIndex = self.findCalset(start, end, self.zeroTableStart,
                                       self.zeroTableEnd, 'zero')
        self.sidebandCalIndex = self.findCalset(start, end,
                                           self.sidebandCarrierStart,
                                           self.sidebandCarrierEnd,
                                           'sideband')
        

    def findCalset(self, rangeStart, rangeEnd, calStarts, calEnds, calType):
        badness = max([0*calStarts, calStarts-rangeStart,
                       rangeEnd-calEnds], axis=0)
        i = argmin(badness)
        if badness[i] > 0:
            if rangeStart != rangeEnd:
                print 'Warning: None of the loaded %s calsets covers %g to %g GHz.'\
                    % (calType, rangeStart, rangeEnd)
                print 'Selecting the calset that covers most.'
            else:
                print 'Warning: None of the loaded %s calsets covers %g GHz.'\
                    % (calType, rangeStart)
                print 'Selecting the closest calset.'
        return i
        


    def DACzeros(self, carrierFreq):
        """Returns the DAC values for which, at the given carrier frequency,
        the IQmixer output power is smallest."""
        if self.zeroTableI == []:
            return [0,0]
        i = self.zeroCalIndex
        if i is None:
            i = findCalset(carrierFreq, self.zeroTableStart, self.zeroTableEnd,
                           'zero')
        carrierFreq = (carrierFreq - self.zeroTableStart[i]) / \
            self.zeroTableStep[i]
        return [interpol(self.zeroTableI[i], carrierFreq), \
                interpol(self.zeroTableQ[i], carrierFreq)]



    def _IQcompensation(self, carrierFreq, n):

        """
        Returns the sideband correction at the given carrierFreq and for
        sideband frequencies
        (0, 1, 2, ..., n/2, n/2+1-n, ..., -1, 0) * (1.0 / n) GHz
        """
        if self.sidebandCompensation == []:
            return zeros(n+1, dtype = complex)
        i = self.sidebandCalIndex
        if i is None:
            i = findCalset(carrierFreq,
                           self.sidebandCarrierStart,
                           self.sidebandCarrierEnd, 'sideband')
        carrierFreq = (carrierFreq - self.sidebandCarrierStart[i]) / \
            self.sidebandCarrierStep[i]
        w=shape(self.sidebandCompensation[i])[1]
        maxfreq= 0.5 * self.sidebandStep[i] * (w-1)
        p=self.sidebandStep[i]/(1-2*maxfreq)
        freqs=zeros(n+1,dtype=float)
        freqs[1:n/2+1]=arange(1,n/2+1)
        freqs[n/2+1:n]=arange(n/2+1-n,0)
        freqs/=n
        compensation = zeros(w+2,complex)
        compensation[1:w+1] = interpol(self.sidebandCompensation[i],carrierFreq)
        compensation[0]   = (1 - p) * compensation[1] + p * compensation[w]
        compensation[w+1] = (1 - p) * compensation[w] + p * compensation[1]
        return interpol(compensation, \
            (freqs + maxfreq + self.sidebandStep[i]) / self.sidebandStep[i], \
            extrapolate=True)



    def _deconvolve(self, carrierfreq, i, loop=False, iqcor=True):

        """
        Deconvolves the signal i with the stored response function and
        if iqcor=True, perform IQ mixer compensation at given carrier frequency.

        If loop=True the fft is performed directly on the signal, otherwise the
        signal is padded with 0 to obtain a signal length for which fft is
        faster. The return value always has the same length as i, however.
        """

        n=alen(i)
        if loop:
            nfft=n
        else:
            nfft=fastfftlen(n)
        nrfft=nfft/2+1

        #FT the input
        signal=zeros(nfft+1,dtype=complex)
        signal[0:nfft]=fft(i,n=nfft)
        #add the first point at the end so that the elements of signal and
        #signal[::-1] are the Fourier components at opposite frequencies
        signal[nfft]=signal[0]

        #correct for the non-orthoganality of the IQ channels
        if iqcor:
            signal += signal[::-1].conjugate() * \
                      self._IQcompensation(carrierfreq, nfft)

        #separate I (FT of a real signal) and Q (FT of an imaginary signal)
        i =  0.5  * (signal[0:nrfft] + signal[nfft:nfft-nrfft:-1].conjugate())
        q = -0.5j * (signal[0:nrfft] - signal[nfft:nfft-nrfft:-1].conjugate())

        #resample the FT of the response function at intervals 1 ns / nfft
        l=alen(self.correctionI)
        freqs = arange(0,nrfft) * 2.0 * (l - 1.0) / nfft
        correctionI = interpol(self.correctionI, freqs, extrapolate=True)
        correctionQ = interpol(self.correctionQ, freqs, extrapolate=True)
        #do the actual deconvolution and transform back to time space
        lp = self.lowpass(nrfft, self.bandwidth)
        i=irfft(i*correctionI*lp, n=nfft)
        q=irfft(q*correctionQ*lp, n=nfft)

        return [i[0:n],q[0:n]]



    def DACify(self, carrierFreq, i, q=None, loop=False, rescale=False, \
               zerocor=True, deconv=True, iqcor=True, zipSRAM=True):

        """
        Computes a SRAM sequence from I and Q values in the range from -1 to 1
        If Q is omitted, the imaginary part of I sets the Q value

        Perfroms the following corrections at the given carrier frequency
        (in GHz):
            - DAC zeros
            - deconvolution with filter chain response
              (For length-1 i and q, this correction cannot be performed)
            - IQ mixer

        DACify only sets the lowest 28 bits of the SRAM samples.
        Add trigger signals to the highest 4 bits via bitwise or when needed.

        If you use deconvolution and unless you have a periodic signal
        (i.e. the signal given to DACify is looped without any dead time),
        you should have at least 5ns before and 20ns after your pulse where
        the signal is 0 (or very small). Otherwise your signal will be deformed
        because the correction for the DAC pulse response will either be clipped
        or wrapped around and appear at the beginning of your signal!


        Keyword arguments:

        loop=True: Does the the FFT on exactly the length of i and q.
            You need this if you have a periodic signal that is non-zero at
            the borders of the signal (like a continous sinewave). Otherwise
            DACify could do the fft on a larger array (padded with 0) in order
            to have a faster fft (fft is fastest for numbers that factorize
            into small numbers)

        rescale=True: If the corrected signal exceeds the DAC range,
            it is rescale to fit. Usefull to drive as hard as possible
            without signal distorsions (e.g. for spectroscopy).
            Otherwise the signal is clipped. After a DACify call
            DACcorrection.last_rescale_factor contains the rescale factor
            actually used. DACcorrection.min_rescale_factor contains the
            smallest rescale factor used so far.

        zerocor=False: Do not perform zero correction.

        deconv=False: Do not perform deconvolution. Sideband frequency
            dependence of the IQ compensation will be ignored.

        iqcor=False: Do not perform IQ mixer correction.

        zipSRAM=False: returns (I,Q) tupels instead of packed SRAM data,
            tupels are not clipped to fit the DAC range.


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
        i = asarray(i)
        if q == None:
            i = i.astype(complex)
        else:
            i= i + 1.0j * q

        #read DAC zeros
        if zerocor:
            [zeroI,zeroQ]=self.DACzeros(carrierFreq)
        else:
            zeroI = zeroQ = 0.0

        if (alen(i)==0):
            return zeros(0)

        if deconv and (self.correctionI != None) and (alen(i) > 1):
            #apply convolution and iq correction
            [i,q]=self._deconvolve(carrierFreq,i,loop=loop,iqcor=iqcor)
        else:
            #only apply iq correction for sideband frequency 0
            if iqcor:
                i += conjugate(i) * self._IQcompensation(carrierFreq,1)[0]
            q=i.imag
            i=i.real

        # for testing uncomment this
        # return [i,q]

        fullscale = 0x1FFF / self.dynamicReserve

        if rescale:
            rescale = min([1.0, \
                           ( 0x1FFF - zeroI) / fullscale / max(i), \
                           (-0x2000 - zeroI) / fullscale / min(i), \
                           ( 0x1FFF - zeroQ) / fullscale / max(q), \
                           (-0x2000 - zeroQ) / fullscale / min(q)])
            if rescale < 1.0:
                print 'Corrected signal scaled by %g to fit DAC range.'
            # keep track of rescaling in the object data
            self.last_rescale_factor = rescale
            if not isinstance(self.min_rescale_factor, float) or rescale < self.min_rescale_factor:
                self.min_rescale_factor = rescale
            fullscale *= rescale


        i = round(i * fullscale + zeroI).astype(int32)
        q = round(q * fullscale + zeroQ).astype(int32)

        if not zipSRAM:
            return (i, q)

        if not rescale:
            if (max(i) > 0x1FFF) or (min(i) < -0x2000):
                print 'Corrected I signal beyond DAC range, clipping.'
                i = clip(i,-0x2000,0x1FFF)
            if (max(q) > 0x1FFF) or (min(q) < -0x2000):
                print 'Corrected Q signal beyond DAC range, clipping.'
                q = clip(q,-0x2000,0x1FFF)

        return ((i & 0x3FFF) << (14 * self.flipChannels) | \
                (q & 0x3FFF) << (14 * (not self.flipChannels))).astype(uint32)





#############################################
#                                           #
# Correction class for a single DAC channel #
#                                           #
#############################################



class DACcorrection:


    def __init__(self, board, lowpass = gaussfilter, bandwidth = 0.13):

        """
        Returns a DACcorrection object for the given DAC board.
        keywords:
            lowpass = func:
                Sets the low pass filter function, i.e. the transfer
                function we want after correction. It expects func of form
                func(n, bandwidth). n is the number of samples between 0
                frequency and the Nyquist frequency (half the sample freq).
                bandwidth is all the other parameters the function needs,
                they are passed to func just as specified by the bandwidth keyword
                to DACcorrection. The return value is the transmission (between 0 and 1)
                at f=0, 1/N, ... (n-1)/N where N is the Nyquist frequency.
                Default: gaussfilter
            bandwidth:
                bandwidth are arguments passed to the lowpass filter function
                (see above)

        """

        self.board = board
        #Set dynamic reserve
        self.dynamicReserve=2.0

        #Use this to see how much the last DACify call rescaled the output
        self.last_rescale_factor = 1.0
        #Use this to see the smallest rescale factor DACify had to use
        self.min_rescale_factor = 1.0


        # Set the Lowpass, i.e. the transfer function we want after correction

        if lowpass == False:
            lowpass = flatfilter

        self.lowpass = lowpass
        self.bandwidth = 0.13

        self.correction = None

        self.zero = 0.0

        self.clicsPerVolt = None


    def loadCal(self, dataPoints, zero = 0.0 , clicsPerVolt = None):
        """
        Reads a pulse calibration file from the data server.
        The result is inverted and multiplied with a lowpass filter, that rolls
        off between 0.5-cufoffwidth GHz and 0.5 GHz.
        It is stored in self.correctionI and self.correctionQ.
        """

        #read pulse calibration from data server


        samplingfreq=int(round(1.0/(dataPoints[1,0]-dataPoints[0,0])))
        dataPoints=dataPoints[:,1]

        #length for fft, long because we want good frequency resolution
        finalLength=10240
        n=finalLength*samplingfreq

        #go to frequency space
        dataPoints=rfft(dataPoints,n=n)
        self.zero = zero
        self.clicsPerVolt = clicsPerVolt
        self.correction = abs(dataPoints[0]) / dataPoints[0:finalLength/2+1]



    def _deconvolve(self, signal, loop=False):

        """
        Deconvolves the signal i with the stored response function.
        If loop=True the fft is performed directly on the signal, otherwise the
        signal is padded with 0 to obtain a signal length for which fft is
        faster. The return value always has the same length as i, however.
        """

        n=alen(signal)

        if loop:
            nfft=n
        else:
            nfft=fastfftlen(n)

        nrfft=nfft/2+1

        #FT the input
        signal=rfft(signal, n=nfft)

        l=alen(self.correction)
        freqs = arange(0,nrfft) * 2.0 * (l - 1.0) / nfft
        correction = interpol(self.correction, freqs, extrapolate=True)
        #do the actual deconvolution and transform back to time space
        signal=irfft(signal*correction*self.lowpass(nrfft, self.bandwidth),
                     n=nfft)
        return signal[0:n]



    def DACify(self, signal, loop=False, rescale=False, fitRange=True, zerocor=True, deconv=True, volts=True):

        """
        Computes a SRAM sequence from one DAC channel. If volts is True,
        the input is expected in volts. Otherwise inputs of -1 and 1 correspond to the DAC range divided by self.dynamicReserve (default 2). In the latter case, clipping may occur beyond -1 and 1.
        DACify corrects for
          - zero offsets (if zerocor is True)
          - gain (if volts is True)
          - pulse shape (if deconv is True)
        DACify returns a long array in the range -0x2000 to 0x1FFF


        If you use deconvolution and unless you have a periodic signal
        (i.e. the signal given to DACify is looped without any dead time),
        you should have at least 5ns before and 20ns after your pulse where
        the signal is 0 (or very small). Otherwise your signal will be deformed
        because the correction for the DAC pulse response will either be clipped        or wrapped around and appear at the beginning of your signal!


        Keyword arguments:

        loop=True: Does the the FFT on exactly the length of the input
            signal.  You need this if you have a periodic signal that
            is non-zero at the borders of the signal (like a continous
            sinewave). Otherwise DACify pads the input with 0 to
            optain a signal length for which fft is fast (fft is
            fastest for numbers that factorize into small numbers)

        rescale=True: If the corrected signal exceeds the DAC range,
            it is rescale to fit. Usefull to drive as hard as possible
            without signal distorsions (e.g. for spectroscopy).
            Otherwise the signal is clipped. After a DACify call
            DACcorrection.last_rescale_factor contains the rescale factor
            actually used. DACcorrection.min_rescale_factor contains the
            smallest rescale factor used so far.
        fitRange=False: Do not clip data to fit into 14 bits. Only effective
            without rescaling.

        zerocor=False: Do not perform zero correction.

        deconv=False: Do not perform deconvolution.

        volts=False: Do not correct the gain. 1 corresponds to
            DACrange/dynamicReserve

         """

        signal = asarray(signal)

        if (alen(signal)==0):
            return zeros(0)

        #read DAC zeros
        if zerocor:
            zero = self.zero
        else:
            zero = 0

        if deconv and (self.correction != None) and (alen(signal) > 1):
            #apply convolution and iq correction
            signal = self._deconvolve(signal,loop=loop)

        # for testing uncomment this
        # return signal
        if volts and self.clicsPerVolt:
            fullscale = 0x1FFF / self.clicsPerVolt
        else:
            fullscale = 0x1FFF / self.dynamicReserve
        if rescale:
            rescale = min([1.0, \
                           ( 0x1FFF - zero) / fullscale / max(signal), \
                           (-0x2000 - zero) / fullscale / min(signal)])
            if rescale < 1.0:
                print 'Corrected signal scaled by %g to fit DAC range.'
            # keep track of rescaling in the object data
            self.last_rescale_factor = rescale
            if not isinstance(self.min_rescale_factor, float) or rescale < self.min_rescale_factor:
                self.min_rescale_factor = rescale
            fullscale *= rescale

        signal = round(signal * fullscale + zero).astype(int32)

        if fitRange and not rescale :
            if (max(signal) > 0x1FFF) or (min(signal) < -0x2000):
                print 'Corrected signal beyond DAC range, clipping.'

                signal = clip(signal,-0x2000,0x1FFF)
        return (signal & 0x3FFF).astype(uint32)




    def recalibrate(self, carrierMin, carrierMax, zeroCarrierStep=0.02,
                sidebandCarrierStep=0.05, sidebandMax=0.35, sidebandStep=0.05):
        if self.recalibrationRoutine is None:
            print 'No calibration routine hooked in.'
            return self
        return self.recalibrationRoutine(self.boardname, carrierMin, carrierMax,
                                         zeroCarrierStep, sidebandCarrierStep,
                                         sidebandMax, sidebandStep, self)
        
