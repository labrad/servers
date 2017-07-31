import labrad
from numpy import *
from scipy.optimize import leastsq
from scipy.optimize.optimize import brute,fmin


import fitting

class spectroscopy_data:
    """A class for wrapping up the functionality and data associated with a spectrscopy fit."""
    
    frequency = array([])  # immutable source array
    frequency_step = 0
    s_amplitude = array([])  # immutable source array
    stats = 0
    
    fits = [] # list of fits (a fit is a ndarray of [amplitude,gamma,x0,baseline]
    c_amplitude = array([])    # current state, i.e. s_amplitude minus all of the fits (baseline is left out of the subtraction)

    mean = 0
    std = 0
    target_std = 0
    imgout = 0

    def __init__(self,frequency,amplitude,stats):
        self.fits = []
        self.frequency = frequency.copy()
        self.s_amplitude = amplitude.copy()
        self.frequency_step = self.frequency[2] - self.frequency[0]
        self.stats = stats
##        print "Stats: ",stats
        self.c_amplitude = self.s_amplitude.copy()
        self.mean = self.c_amplitude.mean()
        self.std = self.c_amplitude.std()
        self.imgout = 0
##        print "Mean: ",self.mean
        self.target_std = 100.0*sqrt(self.mean*(100.0-self.mean)/(10000.0*self.stats))
    
    def add_fit(self,parameters):
        if not isinstance(parameters,ndarray) or len(parameters)!=4:
            raise "parameters must be a ndarray of length 4"

        self.fits.append(parameters)

        self.c_amplitude -= fitting.lorenzian(parameters,self.frequency,{'baseline':0})
        
        self.mean = self.c_amplitude.mean()
        self.std = self.c_amplitude.std()
        self.target_std = 100.0*sqrt(self.mean*(100.0-self.mean)/(10000.0*self.stats))

    def remove_fit(self,index):
        fit = self.fits[index]

        self.c_amplitude += fitting.lorenzian(fit,self.frequency,{'baseline':0})
        
        self.mean = self.c_amplitude.mean()
        self.std = self.c_amplitude.std()
        self.target_std = 100.0*sqrt(self.mean*(100.0-self.mean)/(10000.0*self.stats))

        self.fits.pop(index)

        return fit

    def re_fit(self,index):
        params = self.remove_fit(index)
        return self.fit_params(params)

    def __seek_halfmax__(self,n,direction):
        half_max = (self.c_amplitude[n]-self.mean)/2+self.mean
        i = n
        while self.c_amplitude[i] > half_max:
            i+=direction
        return self.frequency[i]

    def fit_params(self,p0):
        p,fopt,itercnt,funccall,warnflag = fmin(fitting.chi,p0,args=[self.c_amplitude,self.frequency,fitting.lorenzian],full_output=1)
        args = {}
##        print "Amplitude ",p0[0]," => ",p[0]
##        print "Gamma     ",p0[1]," => ",p[1]
##        print "Frequency ",p0[2]," => ",p[2]
##        print "Baseline ",p0[3]," => ",p[3]
##        print "CHI      ",fitting.chi(p0,self.c_amplitude,self.frequency,fitting.lorenzian)," => ",fopt

        if p[0] < p0[0]/2:
##            print "Will toss fit, amplitude lowers too much"
            return None

        prestd = self.std
        
##        plot(self.frequency,self.c_amplitude.copy(),label="before")
##        plot(self.frequency,self.c_amplitude-fitting.lorenzian(p,self.frequency,{'baseline':0}),label="after")
##        plot(self.frequency,fitting.lorenzian(p,self.frequency,args),label="fit")
##        plot(self.frequency,fitting.lorenzian(p0,self.frequency,args),label="prefit")
##
##        legend()
##        savefig('fseq.'+str(self.imgout)+".png")
##        self.imgout += 1
##        cla()

        freqwidth = self.frequency_step
        if p[1]/2 > freqwidth:
           freqwidth = p[1]/2
        
        if(abs(p[2] - p0[2]) > freqwidth):
            #print "Fit has strayed from x0, from",p0[2]," to ",p[2]," larger than ",freqwidth
            return None
            
        self.add_fit(p)
        #print "STD:   ",prestd," => ",self.std," (target = ",self.target_std,")"
        return p
    
    def new_fit(self):
        #print "Std: ",self.std," Target: ",self.target_std;

        n = self.c_amplitude.argmax()
        amp = self.c_amplitude[n];
        freq = self.frequency[n];

        if abs(amp - self.mean) < 2*self.std:
            return None
        
        if self.std < self.target_std and abs(amp-self.mean) < 4*self.std:
           return None

        
        print "Make new fit"
        

        xleft = self.__seek_halfmax__(n,-1)
        xright = self.__seek_halfmax__(n,1)
        
        p0 = [amp-self.mean,(xright-xleft)*0.5,freq,self.mean-self.std/2]
        
        return self.fit_params(p0)

    def fit(self):
        if self.mean==0 or self.mean==100:
            return
        try:
            while not None == self.new_fit():
                for i in range(len(self.fits)-1,-1,-1):
                    self.re_fit(i)
        except:
            self.fits=[]
