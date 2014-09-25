import labrad
import re
import pylab
from numpy import *
from dv_search import dv_search
import sys,traceback
import fitting

class step_edge_fit:
    def __init__(self,amplitude,probability):
        self.s_amplitude = array(amplitude)
        self.s_probability = array(probability)

    def calc_slopes(self):
        self.slopes = self.s_probability[:-1]-self.s_probability[1:]
        self.slopes_std = self.slopes.std()
        self.slopes_mean = self.slopes.mean()
        self.slopes_var = self.slopes.var()

        if self.slopes_var == 0:
            raise "No variance in data: Nothing to do."

        self.index_width_rough_estimate = 100.0/(self.slopes.var())
        print 'Slopes Mean: ',self.slopes_mean;
        print 'Slopes Std:  ',self.slopes_std;
        print 'Slopes Variance: ',self.slopes_var;
        
        print 'Index width (rough estimate): ',self.index_width_rough_estimate

        self.probability_smooth = fitting.smooth(self.s_probability,math.floor(self.index_width_rough_estimate))
        self.slopes_smooth = self.probability_smooth[:-1] - self.probability_smooth[1:]
        self.slopes_smooth_std = self.slopes_smooth.std()
        self.slopes_smooth_mean = self.slopes_smooth.mean()

    def calc_envelope(self,data,direction):
        minV = data.max()
        maxV = data.min()

        minA = zeros(len(data))
        maxA = zeros(len(data))
        
        if direction==-1:
            r = range(len(data)-1,-1,-1)
        if direction==1:
            r = range(0,len(data),1)
        
        for i in r:
            v = data[i]
            if v > maxV:
                maxV = v
            if v < minV:
                minV = v

            minA[i] = minV
            maxA[i] = maxV

        return (minA,maxA)

    def range_for_dir(self,direction):
        if(direction == 1):
            return range(0,len(self.s_probability),1)
        elif direction==-1:
            return range(len(self.s_probability)-1,-1,-1)
        else:
            return None

    def fit_rough_lims(self):
        # find start
        mini = self.min_envelope.min()
        maxi = self.max_envelope.max()
        
        for i in self.range_for_dir(self.direction):
            if self.min_envelope[i] > mini:
                self.startarg = i-self.direction
                break;

        for i in self.range_for_dir(-self.direction):
            if self.max_envelope[i] < maxi:
                self.endarg = i+self.direction
                break;

        self.end = self.s_amplitude[self.endarg];
        self.start = self.s_amplitude[self.startarg];

    def fit_refine_lims(self):
        if self.direction == 1:
            highstd = self.s_amplitude[self.end:-1].std()
            self.highmean = self.s_probability[self.endarg:-1].mean()
            lowstd = self.s_amplitude[0:self.start].std()
            self.lowmean = self.s_probability[0:self.startarg].mean()
        elif self.direction == -1:
            highstd = self.s_amplitude[0:self.end].std()
            self.highmean = self.s_probability[0:self.endarg].mean()
            lowstd = self.s_amplitude[self.start:-1].std()
            self.lowmean = self.s_probability[self.startarg:-1].mean()
        else:
            print "Direction wonky: ",self.direction
            return
        
        print 'Total mean: ',self.s_probability.mean()
        print 'Low mean: ',self.lowmean,' high mean: ',self.highmean
        
        for i in self.range_for_dir(self.direction):
            if self.min_envelope[i] > self.lowmean+lowstd:
                self.startarg = i-self.direction
                print 'Found low'
                break;

        for i in self.range_for_dir(-self.direction):
            if self.max_envelope[i] < self.highmean-highstd:
                self.endarg = i+self.direction
                print 'found high'
                break;

        self.end = self.s_amplitude[self.endarg];
        self.start = self.s_amplitude[self.startarg];

    def fit_percent(self,pc=5):
        for f in self.range_for_dir(self.direction):
            if self.probability_smooth[f] > pc:
                slope = (self.probability_smooth[f]-self.probability_smooth[f-self.direction])/(self.s_amplitude[f]-self.s_amplitude[f-self.direction])
                return self.s_amplitude[f-self.direction] + (pc-self.probability_smooth[f-self.direction])/slope
        raise labrad.types.Error("Intercept for "+str(pc)+" does not exist",101)
    
    def fit_envelopes(self):
        ltr = self.calc_envelope(self.s_probability,1)
        rtl = self.calc_envelope(self.s_probability,-1)

        if ltr[0].std() > ltr[1].std() and rtl[0].std() < rtl[1].std():
            self.min_envelope = ltr[0]
            self.max_envelope = rtl[1]
            self.direction = -1
            print "lefgoing"
        elif rtl[0].std() > rtl[1].std() and ltr[0].std() < ltr[1].std():
            self.max_envelope = ltr[1]
            self.min_envelope = rtl[0]
            print "rightgoing"
            self.direction = 1
        else:
            print "neither"
            self.direction = 0

    def fit(self):
        self.calc_slopes()
        
        self.fit_envelopes()
        self.fit_rough_lims()
        self.fit_refine_lims()

if __name__=="__main__":
    cxn = labrad.connect()
    data_vault = cxn.data_vault;

    paths = []

    #paths.append((['','Markus','Experiments','2008/04/26 - Experiment Server Buildup'],11))
    #paths.append((['','Markus','Experiments','2008/05/10 - Check Qubits (Daniel)'],9))
    #paths.append((['','Markus','Experiments','2008/05/10 - Check Qubits (Daniel)'],13))
    #paths.append((['','Markus','Experiments','2008/05/10 - Check Qubits (Daniel)'],14))

    #leftoing ones:

    #paths.append((['','Haohua','RadekQubit3','unknown','080623'],4)) # also has bad start point... way too far out
    #paths.append((['','Markus,'Experiments','2008/04/28 - Coupled Shaped Pulses'],58) # stop point too far out!

    #paths = dv_search(data_vault,re.compile(".*Step.*Edge.*"),[''])
    paths = dv_search(data_vault,re.compile(".*S.*Curve.*"),[''])
            
    skip = 0
    n=0

    try:
        skip = int(sys.argv[1])
    except:
        skip = 0
        
    for path in paths:
        n+=1
        if n < skip:
            continue
        if n == skip:
            print 'Skipped ',skip,' datasets.'
        print 'Fitting n=',n,'(path=',path,')';
        
        try:
            dv = cxn.data_vault.packet()
            dv.cd(path[0])
            dv.open(path[1])
            dv.get(key='data')
            dv.get_parameters(key='params')
            ans = dv.send()
            
            data = ans.data.asarray

            print data.shape
            if data.shape[0] < 10:
                print 'Not enough data!'
                continue;
            
            data_xmin = data[:,0].min()
            data_xmax = data[:,0].max()

            fitobj = step_edge_fit(data[:,0],data[:,1])
            fitobj.fit()
            fitobj.cutoff_5percent = fitobj.fit_percent(5)
            
            #if fitobj.direction == 1:
            #    continue;
            
            pylab.subplot(211)
            pylab.cla()
            
            pylab.title("data");
            
            #pylab.grid()

            pylab.plot(data[:,0],data[:,1],'.',color="blue")
            pylab.plot(data[:,0],fitobj.min_envelope,'-',color="green")
            pylab.plot(data[:,0],fitobj.max_envelope,'-',color='red')
            pylab.plot(data[:,0],fitobj.probability_smooth,':',color='black')

            pylab.plot(array([fitobj.start,fitobj.start]),array([0,100]),'g-',lw=3,alpha=0.4)
            pylab.plot(array([fitobj.end,fitobj.end]),array([0,100]),'r-',lw=3,alpha=0.4)
            
            if fitobj.cutoff_5percent < data[0,0] or data[-1,0] < fitobj.cutoff_5percent:
               print "Bad 5% cutoff..."
            else:
                pylab.plot(array([fitobj.cutoff_5percent,fitobj.cutoff_5percent]),array([0,100]),'b-',lw=3,alpha=0.4)

            pylab.plot(array([data[0,0],data[-1,0]]),array([fitobj.highmean,fitobj.highmean]),':',color="red");
            pylab.plot(array([data[0,0],data[-1,0]]),array([fitobj.lowmean,fitobj.lowmean]),':',color="green");
            ()
            
            pylab.xlim(data_xmin,data_xmax)
            pylab.ylim(-5,105)
            
            pylab.subplot(212)
            pylab.cla()
            
            pylab.title("slopes")
            
            pylab.grid()
            pylab.plot(data[:-1,0],abs(fitobj.slopes/fitobj.slopes_std),'o',color="blue")
            pylab.plot(data[:-1,0],abs(fitobj.slopes_smooth/fitobj.slopes_smooth_std),'-',color="red")
            pylab.xlim(data_xmin,data_xmax)
           
            pylab.show()
            
            raw_input("Waiting...")

            
        except KeyboardInterrupt:
            raise
        except:
            traceback.print_exc(sys.stdout)
            raw_input("Next...");
            continue
        

    print 'Ran through ',n,' datasets'

    cxn.disconnect()
