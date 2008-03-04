from numpy import conjugate, array, asarray, floor, ceil, round, min, max, \
alen, clip, sqrt, log, arange, zeros, ones, reshape, outer, compress, sum, \
shape, cos, pi, exp
from numpy.fft import fft, rfft, irfft
import dms
#from pylab import plot, show

VERSION = '20070726'
SETUPTYPESTRINGS = ['no IQ mixer', \
                    'DAC A -> mixer I, DAC B -> mixer Q',\
                    'DAC A -> mixer Q, DAC B -> mixer I']
SESSIONNAME = 'GHzDAC Calibration'
ZERONAME = ' - zero'
PULSENAME = ' - pulse'
IQNAME = ' - IQ'



def cosinefilter(n, width=0.4):
    """cosinefilter(n,width) cosine lowpass filter
    n samples from 0 to 0.5 GHz
    1 from 0 GHz to width GHz
    rolls of from width GHz to 0.5 GHz like a quater cosine wave""" 
    result = ones(n,dtype=float)
    width = int(round((0.5-width)*n*2.0))
    if width > 0:
        result[n-width:] = 0.5+0.5*cos(arange(0.0,pi,pi/width))
    return result



def gaussfilter(n, width=0.13):
    """ lowpassfilter(n,width) gaussian lowpass filter.
    n samples from 0 to 0.5 GHz
    -3dB frequency at width GHz
    """
    x=0.5 / width * sqrt(log(2.0)/2.0)
    gauss=exp(-arange(0,x,x/n)**2)
 #   x=gauss[n-1]
 #   gauss -= x

    #gauss /= (1.0 - x)
    return gauss



def spect_config(spec,bw,center,span):
    """
    Configure the spectrum analyzer spec to bandwidth bw,
    centerfrequency center and span span.
    """
    spec.gpib_write(':AVER:STAT OFF\n:POW:RF:ATT:AUTO\n:BAND %g%s\n:FREQ:SPAN %g%s\n:FREQ:CENT %g%s\n:INIT:CONT ON\n' % (bw[0],bw[1],span[0],span[1],center[0],center[1]))



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
    i = floor(x).astype(int)
    n = alen(signal)
    i = clip(i, 0, n-2)
    p = x - i
    if not extrapolate:
        p = clip(p,0.0,1.0)
    return signal[i] * (1.0 - p) + signal[i+1] * p



class DACcorrection:

    def __init__(self, fpganame, connection = None, \
                 lowpass = None, lowpasswidth = None):

        """
        Returns a DACcorrection object for the given DAC board.
        The argument has the same form as the
        dms.python_fpga_server.connect argument
        """

        print 'Version %s' % VERSION

        #Set dynamic reserve
        self.dynamicReserve=2.0

        #Use this to see how much the last DACify call rescaled the output
        self.last_rescale_factor = 1.0
        #Use this to see the smallest rescale factor DACify had to use
        self.min_rescale_factor = 1.0


        cxn=connection or dms.connect()
        ds=cxn.data_server()
        ctx = ds.context()
        
        ds.open_session(SESSIONNAME,context=ctx)
        dslist=ds.list_datasets(context=ctx)[0]

        #Load pulse response

        index=len(dslist)-1
        while (index >=0) and (not dslist[index][8:] == fpganame + PULSENAME):
            index-=1
        if index < 0:
            setupType = 2
            print 'Warning: No pulse calibration found for %s.' % fpganame
            print '         No deconvolution will be performed.'
            print '         Assuming %s.' % SETUPTYPESTRINGS[setupType]
            self.correctionI=None
            self.correctionQ=None
            self.IisB = (setupType == 2)
        else:
            print 'Loading pulse calibration from %s...' % dslist[index]
            ds.open_dataset(dslist[index],context=ctx)
            setupType = int(round(\
                ds.get_parameter('Setup type',context=ctx)[0].value))
            print '  %s' % SETUPTYPESTRINGS[setupType]
            self.IisB = (setupType == 2)

            if setupType > 0:
                self._demodulatepulseresponse(ds, ctx)
                # if we have an IQ mixer we use smooth signals up to
                # high frequencies so we want a flat filter function
                # up to high frequency.
                if lowpass == None:
                    lowpass = cosinefilter
                if lowpasswidth == None:
                    lowpasswidth = 0.4
            else:
                self._loadresponse(ds,ctx)
                # if we do not have a IQ mixer we probably want rectangular
                # pulses so we want a non-ringing response function
                if lowpass == None:
                    lowpass = gaussfilter
                if lowpasswidth == None:
                    lowpasswidth = 0.15
            if lowpass != 0:
                lowpass = lowpass(alen(self.correctionI),lowpasswidth)
                self.correctionI*=lowpass
                self.correctionQ*=lowpass
            self.correctionI /= clip(abs(self.correctionI)/3/self.dynamicReserve,1.0,1e1000)
            self.correctionQ /= clip(abs(self.correctionQ)/3/self.dynamicReserve,1.0,1e1000)

        #Load zero calibration
        if setupType > 0:
            index=len(dslist)-1
        #no zero calibration when there is no IQ mixer
        else:
            index = -1
        while (index >= 0) and (not dslist[index][8:] == fpganame + ZERONAME):
            index-=1

        if index < 0:
            if setupType > 0:
                print 'Warning: No zero calibration found for %s.' % fpganame
                print '         DAC offsets set to zero.'
            self.zeroTableStart = 0.0
            self.zeroTableStep = 1e6
            self.zeroTableI = self.zeroTableQ = array([0,0])
        else:
            print 'Loading zero calibration from %s...' % dslist[index]
            ds.open_dataset(dslist[index],context=ctx)
            x = ds.get_all_datapoints(context=ctx)[0].values
            self.zeroTableI = asarray(x[1+self.IisB::3])
            self.zeroTableQ = asarray(x[1+(not self.IisB)::3])
            x = x[0::3]
            l = len(x)
            self.zeroTableStart=x[0]
            self.zeroTableStep=(x[-1]-x[0])/(l-1)
            print '  carrier frequencies: %g GHz to %g GHz in steps of %g MHz' % \
                (x[0], x[-1], self.zeroTableStep*1000.0)

            zeroMax=max([abs(self.zeroTableI).max(),abs(self.zeroTableQ).max()])

     
        #Load IQ dideband mixing calibration
        if setupType > 0:
            index=len(dslist)-1
        else:
            index = -1
        while (index >= 0) and (not dslist[index][8:] == fpganame + IQNAME):
            index-=1


        if index < 0:
            if setupType > 0:
                print 'Warning: No sideband mixing calibrations found for %s.' % fpganame
                print '         No IQ mixer corrections will be performed.'
            self.sidebandCompensation = None
        else:
            print 'Loading sideband mixing calibration from %s...' % dslist[index]
            ds.open_dataset(dslist[index],context=ctx)
            self.sidebandStep = ds.get_parameter('Sideband frequency step [GHz]',context=ctx)[0].value
            w = int(round(ds.get_parameter('Number of sideband frequencies',context=ctx)[0].value))
            x = asarray(ds.get_all_datapoints(context=ctx)[0].values)
            l=alen(x)/(2*w+1)
            x=reshape(x, (l,2*w+1))
            self.sidebandCarrierStart=x[0,0]
            self.sidebandCarrierStep=(x[-1,0]-x[0,0])/(l-1)
            print '  carrier frequencies: %g GHz to %g GHz in steps of %g MHz' % \
                (x[0,0], x[-1,0], self.sidebandCarrierStep*1000.0)
            x = reshape(x[:,1:],(l,w,2))
            self.sidebandCompensation = x[:,:,0]+1.0j*x[:,:,1]
            print '  sideband frequencies: %g MHz to %g Mhz in steps of %g MHz' % \
                (-500.0*(w-1)*self.sidebandStep, 500.0*(w-1)*self.sidebandStep, \
                self.sidebandStep*1000)

    
 
        if not connection:
            cxn.disconnect()



    def _loadresponse(self,ds,ctx):
        """
        Reads a pulse calibration file from the data server.
        The result is inverted and multiplied with a lowpass filter, that rolls
        off between 0.5-cufoffwidth GHz and 0.5 GHz.
        It is stored in self.correctionI and self.correctionQ.
        """

        #read pulse calibration from data server
        datapoints=ds.get_all_datapoints(context=ctx)[0].values
        i=datapoints[1::3]
        q=datapoints[2::3]
        length=len(i)
        samplingfreq=int(1/((datapoints[-3]-datapoints[0])/(len(i)-1))+0.5)
        datapoints=None

        #length for fft, long because we want good frequency resolution
        finalLength=10240
        n=finalLength*samplingfreq
        print '  sampling frequency: %d GHz' % samplingfreq

        #go to frequency space
        i=rfft(i,n=n)
        q=rfft(q,n=n)
   
        self.correctionI = abs(i[0]) / i[0:finalLength/2+1]
        self.correctionQ = abs(q[0]) / q[0:finalLength/2+1]

        

    def _demodulatepulseresponse(self,ds,ctx):

        """
        Reads a pulse calibration file from the data server and
        demodulates the IQ mixer output with the carrier frequency.
        The result is inverted and multiplied with a lowpass filter, that rolls
        off between 0.5-cufoffwidth GHz and 0.5 GHz.
        It is stored in self.correctionI and self.correctionQ.
        """

        #read pulse calibration from data server
        datapoints=ds.get_all_datapoints(context=ctx)[0].values
        carrierfreq=ds.get_parameter('Anritsu frequency [GHz]',context=ctx)[0].value
        i=datapoints[1 + self.IisB::3]
        q=datapoints[1 + (not self.IisB)::3]
        length=len(i)
        samplingfreq=int(1/((datapoints[-3]-datapoints[0])/(len(i)-1))+0.5)
        datapoints=None

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
     
        self.correctionI = 1.0 / (0.5 / abs(low[0]) * (conjugate(low/phase) + high/phase))

        low = q[carrierfreqIndex:carrierfreqIndex-finalLength/2-1:-1]
        high = q[carrierfreqIndex:carrierfreqIndex+finalLength/2+1:1]
        #calcualte the phase of the carrier
        phase=sqrt(sum(low*high))
        phase/=abs(phase)
        if (conjugate(phase)*low[0]).real < 0:
            phase*=-1
        self.correctionQ = 1.0 / (0.5 / abs(low[0]) * (conjugate(low/phase) + high/phase))
        
        

    

    def DACzeros(self, carrierFreq):
        """Returns the DAC values for which, at the given carrier frequency,
        the IQmixer output power is smallest."""
        carrierFreq = (carrierFreq - self.zeroTableStart) / self.zeroTableStep
        return [interpol(self.zeroTableI, carrierFreq), \
                interpol(self.zeroTableQ, carrierFreq)]
     


    def _IQcompensation(self, carrierFreq, n):

        """
        Returns the sideband correction at the given carrierFreq and for
        sideband frequencies
        (0, 1, 2, ..., n/2, n/2+1-n, ..., -1, 0) * (1.0 / n) GHz
        """
        if self.sidebandCompensation == None:
            return zeros(n+1, dtype = complex)
        carrierFreq = (carrierFreq - self.sidebandCarrierStart) / self.sidebandCarrierStep
        w=shape(self.sidebandCompensation)[1]
        maxfreq= 0.5 * self.sidebandStep * (w-1)
        p=self.sidebandStep/(1-2*maxfreq)
        freqs=zeros(n+1,dtype=float)
        freqs[1:n/2+1]=arange(1,n/2+1)
        freqs[n/2+1:n]=arange(n/2+1-n,0)
        freqs/=n
        compensation = zeros(w+2,complex)
        compensation[1:w+1] = interpol(self.sidebandCompensation,carrierFreq)
        compensation[0]   = (1 - p) * compensation[1] + p * compensation[w]
        compensation[w+1] = (1 - p) * compensation[w] + p * compensation[1]
        return interpol(compensation, \
            (freqs + maxfreq + self.sidebandStep) / self.sidebandStep, \
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
        i=irfft(i*correctionI,n=nfft)
        q=irfft(q*correctionQ,n=nfft)
        
        return [i[0:n],q[0:n]]



    def DACify(self, carrierFreq, i, q = None, loop=False, rescale=False, \
               zerocor=True, deconv=True, iqcor=True):

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
                            
        
        i = round(i * fullscale + zeroI).astype(long)
        q = round(q * fullscale + zeroQ).astype(long)

        if not rescale:
            if (max(i) > 0x1FFF) or (min(i) < -0x2000):
                print 'Corrected I signal beyond DAC range, clipping.'
                i = clip(i,-0x2000,0x1FFF)
            if (max(q) > 0x1FFF) or (min(q) < -0x2000):
                print 'Corrected Q signal beyond DAC range, clipping.'
                q = clip(q,-0x2000,0x1FFF)

        return ((i & 0x3FFF) << (14 * self.IisB) | \
                (q & 0x3FFF) << (14 * (not self.IisB))).tolist()


        
        
        
    
