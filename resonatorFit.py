# Copyright (C) 2007  Markus Ansmann
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
name = Resonator Fit
version = 0.1.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

#Import the LabradServer superclass
from labrad.server import LabradServer, setting
from labrad import util 
#Import some math functions
import numpy
from numpy import pi, sqrt, exp, array
from scipy import optimize, interpolate
from matplotlib import pyplot

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from time import sleep

class ResonatorFit(LabradServer):
    """This server fits resonator data to determine Q, f0, etc."""
    name = "resonatorfit"
    
    
    
    @inlineCallbacks
    def open_s21(self, dir, filenum):
    #Opens a data vault file and pulls out the S21 data as an array in the format (frequency, complex S21).
    
        dv=self.client.data_vault
        
        #Goes to the correct directory.
        yield dv.cd([''])
        yield dv.cd(dir)
        yield dv.open(filenum)
        
        datafromfileraw = yield dv.get(10**3)
        newdata = numpy.asarray(datafromfileraw)
        nrows,ncols = newdata.shape
        datafromfile=numpy.empty([0,ncols])
        while (nrows>0.5 and ncols>0.5):
            datafromfile= numpy.concatenate((datafromfile,newdata),axis=0)
            datafromfileraw = yield dv.get(10**3)
            newdata = numpy.asarray(datafromfileraw)
            nrows,ncols = newdata.shape
        
        #Saves S21 data into numpy array. If no S21 data, then displays error and quits program.
        varsraw = yield dv.variables()
        vars = varsraw[1]
        magcol = -1
        phasecol = -1
        for strnum in range(len(vars)):
            if vars[strnum][1] == 'S21':
                if vars[strnum][0] == 'Magnitude':
                    magcol = strnum+1
                    break
        else:
            print 'Did not measure magnitude of S21.'
            return
        for strnum in range(len(vars)):
            if vars[strnum][1] == 'S21':
                if vars[strnum][0] == 'Phase':
                    phasecol = strnum+1
                    break
        else:
            print 'Did not measure phase of S21.'
            return
        mag = 10**(datafromfile[:,magcol]/20.)
        complexval = mag*exp(1j*datafromfile[:,phasecol]) 
        data = array([datafromfile[:,0],complexval])
        returnValue(data)
    
    
    
    def thru_residues(self,parm,z,frequency):
    #Fit function for through-resonators (resonator between two coupling capacitors)
        return abs(z + exp(1j*parm[0])*(1+parm[1]/parm[2])**(-1)*(1+2j*(1/parm[1]+1/parm[2])**(-1)*(frequency-parm[3])*parm[3]**(-1))**(-1) - (parm[4]+1j*parm[5]))
    
    
    
    @inlineCallbacks
    def calibrate_data(self, datain, cal, range, background):
    #Calibrate input data using calibration file calfile in caldir
    
        # If only wanting to fit a limited range, select data with frequencies in this range
        if range[0]:
            frangein = datain[0]
            frangecut = numpy.logical_and(frangein>range[1],frangein<range[2])
            check = False
            for item in frangecut:
                check=numpy.logical_or(check,item)
            if check:
                frange = frangein[frangecut]
                zrange = datain[1][frangecut]
                datain = array([frange,zrange])
        
        # Calibrate data if desired
        if cal[0]:
            # Open calibration file
            calopen = yield self.open_s21(cal[1],cal[2])
            if (datain[0].min()>=calopen[0].min() and datain[0].max()<=calopen[0].max()):
                calfreqfull = calopen[0]
                calcut = numpy.logical_and(calfreqfull>=(0.9*datain[0].min()),calfreqfull<=(1.1*datain[0].max()))
                calinterp = interpolate.interp1d(calopen[0][calcut],calopen[1][calcut])
                caldata = array([datain[0],datain[1]/calinterp(datain[0])])
            else:
                caldata = datain
        else:
            caldata = datain
        
        returnValue(caldata)
    
    
    
    def resonant_fit(self, frequency, z, shunt):
    #Fits a single calibrated S21 trace."""

        # The following calculates the center of the resonance in the complex plane.
        # The basic idea is to find the mean of the max and the min of both the realz
        # and imagz.  This would give the center of the circle if this were a true
        # circle.  However, since the resonance is not a circle we find the center by
        # rotating the resonance by an angle, finding the mean of the max and the min
        # of both the realz and imagz of the rotated circle, then rotating this new
        # point back to the original orientation. Finally, the middle of the resonance
        # is given by finding the mean of all these rotated back ave max min values.
        # Note: we only need to rotate a quarter of a turn because anything over
        # that would be redundant.
        
        steps = 100
        centerpoints = array(range(steps),dtype=complex)
        for ang in range(steps):
            rotation = exp((2j * pi * (ang+1) / steps) / 4) # the 4 here is for a quarter turn
            zrot = rotation*z
            re = (zrot.real.max() + zrot.real.min()) / 2.
            im = (zrot.imag.max() + zrot.imag.min()) / 2.
            centerpoints[ang] = complex(re,im) / rotation # here the new center point is rotated back
        center=centerpoints.mean();

        # Finding an estimate for the diameter of a circle that would fit the
        # resonance data
        diameter = 2 * abs(z - center).mean()

        # Finding the stray coupling
        # First a rough estimate of the stray is found by averaging all the points,
        # utilizing the fact that most of the points are located near the origin.
        # Then, a unit vector A is created that points from the center to the stray
        # Finally, the stray is found by taking the point at the tip of a vector
        # from the center, the length of the diameter, in the direction of A.

        stray = z.mean()
        A = (stray - center) / abs(center - stray)
        stray = center + A * diameter / 2

        # This finds an aproximation to the resonant frequncy located at an angle of zero
        # and the frequency of the 3dB points which are located at pi/2 and -pi/2.
        # We also calculate an aproximatin for Q from John's paper deltaOmega/Omega0 = 1/Q
        
        angles = numpy.angle((center - z) / A)
        anglesrange = numpy.logical_and(angles>-3,angles<3)
        freqinterp = frequency[anglesrange]
        anginterp = angles[anglesrange]
        freqplus = numpy.median(interpolate.sproot(interpolate.splrep(freqinterp,anginterp-(pi/2))))
        freqneg = numpy.median(interpolate.sproot(interpolate.splrep(freqinterp,anginterp-(-pi/2))))
        f0 = numpy.median(interpolate.sproot(interpolate.splrep(freqinterp,anginterp)))
        Q = f0 / (freqneg - freqplus)

        # For the fitting function we will need some other quantaties, namely Qc and
        # Q0.  From John's paper, 1/Q = R0(1/R + 1/Rc), Qc = Rc/R0, and d = 1/(1 + Rc/R).
        # Combining these gives the result Qc = Q/d.

        Qc = Q / diameter

        # To find Q0 we have the equation from John's paper 1/Qi = 1/Q - 1/Qc.  Now
        # with the result we just found for Qc, we have:

        Qi = Q / (1 - diameter)

        # From the quantaties determined above, we can determine a guess function
        # for the parameters of a function to be fit, which we will construct shortly

        angleA = numpy.angle(A)
        guess = array([angleA,Qc,Qi,f0,stray.real,stray.imag])

        # From John's paper s21 = -1/(1+Rc/R) * 1/(1+i*2*Q*(f-f0)/f0 ).  However, this
        # is for the ideal case.  In our case, we have stray coupling (origin shift)
        # and a rotation of the curve.  Putting these factors in we obtain
        # s21 = -exp(i*theta)/(1+Rc/R) * 1/( 1+i2Q(f-f0)/f0 ) + stray.  We note
        # that Rc/R = Qc/Qi and Q = (1/Qc + 1/Qi)^(-1) and we obtain the following
        # s21 = -exp(i*theta)/(1+Qc/Qi) * 1/( 1+i*2*(1/Qc + 1/Qi)^(-1)*(f-f0)/f0 ) + stray

        # Now, to form a minizable quantity we take minimize the sum of the squares
        # of the quantity (s21 measured - s21 as defined above)
        # For the least squares function we will use to find a fit, we will need to
        # create a vector of the parameters to be minimized.  Thus, use for our
        # variables the following elements of a vector "parm" with the following
        # identification
        # parm[0] is theta
        # parm[1]is Qc
        # parm[2] is Qi
        # parm[3] is f0
        # parm[4]+j*parm[5] is stray
        # Thus we need to minimize the following

        least = optimize.leastsq(self.thru_residues,guess,args=(z,frequency),full_output=True)
        lsparm = least[0]
        nparm = 6
        rsd=(least[2]["fvec"]**2).sum()/(len(frequency)-nparm)
        covar = sqrt(rsd*numpy.diag(least[1])).real

        # # The variables are all reassigned to the fit values

        theta = lsparm[0]
        Qc = lsparm[1]
        Qi = lsparm[2]
        f0 = lsparm[3]
        strayRe = lsparm[4]
        strayIm = lsparm[5]
        Q = (1/Qc+1/Qi)**-1
        fit = array([theta, Qc, Qi, Q, f0, strayRe, strayIm])

        thetaerror = covar[0]
        Qcerror = covar[1]
        Qierror = covar[2]
        f0error = covar[3]
        strayerrorRe = covar[4]
        strayerrorIm = covar[5]
        Qerror = (1/(1/Qi+1/Qc)**2)*(Qcerror/Qc**2+Qierror/Qi**2)
        fiterror = array([thetaerror,Qcerror,Qierror,Qerror,f0error,strayerrorRe,strayerrorIm])

        # # We now calculate the max power transmitted on resonance by sampling 500
        # # point of the fitting function, converting the voltage to power, and
        # # finding the maximum of these points.
        
        nPoints = 500
        f = numpy.linspace(frequency[0],frequency[-1],nPoints)
        maxpower_c = (20 * numpy.log10(abs(-exp(1j*theta)/(1+Qc/Qi) * 1./( 1 + 2j*(1/Qc + 1/Qi)**(-1) * (f - f0)/f0 )))).max()

        fitreturn = (fit, fiterror, maxpower_c)
        return fitreturn
    
    
    
    @inlineCallbacks
    def calibrate_fit(self, dirname, filenum, shunt, cal, range, background):
    #Read a single s21 trace, calibrate data, and fit Q
        
        #Read s21 data from s21 from Data Vault into numpy array
        s21={}
        s21['rawdata'] = yield self.open_s21(dirname,filenum)
        
        #Get parameters for this data set
        params = yield self.client.data_vault.get_parameters()
        s21.update(dict(params))
        
        #If data to be calibrated, calibrates data
        if (cal[0] or range[0] or background[0]):
            s21['caldata'] = yield self.calibrate_data(s21['rawdata'],cal,range,background)
        else:
            s21['caldata'] = s21['rawdata']
        
        #Fit resonator data (function depends on what type of resonator)
        s21['maxpowerUncal'] = (20 * numpy.log10(abs(s21['rawdata'][1]))).max()
        (s21['fit'],s21['fiterror'],s21['maxpowerCal']) = self.resonant_fit(s21['caldata'][0].real,s21['caldata'][1],shunt)
        
        returnValue(s21)
    
    
        
    #@setting(10, 'Single Fit', dirname='*s', filenum='w', shunt='b', ifcal='b', caldir='*s', calnum='w', ifrange='s', rangemin='v', rangemax='v', ifback='s', backmin='v', backmax='v', backorder='w', returns='?')
    @setting(10, 'Single Fit', dirname='?', filenum='?', shunt='?', ifcal='?', caldir='?', calnum='?', ifrange='?', rangemin='?', rangemax='?', ifback='?', backmin='?', backmax='?', backorder='?', returns='?')
    def single_fit(self, c, dirname, filenum, shunt, ifcal, caldir, calnum, ifrange, rangemin, rangemax, ifback, backmin, backmax, backorder):
        """Fits a single S21 trace with calibration."""
        fitDict = yield self.calibrate_fit(dirname,filenum,shunt,(ifcal,caldir,calnum),(ifrange,rangemin,rangemax),(ifback,backmin,backmax,backorder))
        returnValue(tuple(fitDict.items()))
            
        
        
    @setting(20, 'Magnitude Plot', data='?', returns='?')
    def magplot(self, c, data):
        """Plots magnitude vs frequency"""
        plotData = data.asarray
        freq=plotData[0].real
        mag=10*numpy.log10(abs(plotData[1]))
        pyplot.plot(freq,mag,'b.')
        pyplot.xlabel('Frequency / GHz')
        pyplot.ylabel('Magnitude of S21 in dB')
        pyplot.show()
        
        
    @setting(21, 'Phase Plot', data='?', returns='?')
    def phplot(self, c, data):
        """Plots phase vs frequency"""
        plotData = data.asarray
        freq=plotData[0].real
        phase=numpy.arctan2(plotData[1].imag,plotData[1].real)*180/pi
        pyplot.plot(freq,phase,'b.')
        pyplot.xlabel('Frequency / GHz')
        pyplot.ylabel('Phase of S21 in degrees')
        pyplot.show()
        
        
    @setting(22, 'Circle Plot', data='?', returns='?')
    def cirplot(self, c, data):
        """Plots phase vs frequency"""
        plotData = data.asarray
        pyplot.plot(plotData[1].real,plotData[1].imag,'b.')
        pyplot.xlabel('Real of S21')
        pyplot.ylabel('Imag of S21')
        pyplot.show()
        
        
        
    
#Run this server if this is being run as a script, not imported by another script.
if __name__=="__main__":
    from labrad import util
    util.runServer(ResonatorFit())