# -*- coding: cp1252 -*-
import labrad
import re
from pylab import *
from numpy import *
from dv_search import dv_search
import sys,traceback


## FUCKUP: (['','Markus','Experiments','2008/04/06 - Check Qubits'],32)

class squid_fit:
    def __init__(self,flux,negative,positive,stats):
        self.s_negative_time = negative
        self.s_positive_time = positive
        self.s_flux = flux
        self.stats = int(stats)

        self.mean = []
        self.std = []
        self.median_derivative = 0
        self.mean_derivative = []
        self.mean_derivative_mean = 0
        self.mean_derivative_std = 0
        self.meansort = []

        self.neg_lines = []
        self.pos_lines = []

        self.shared_lines = []

        self.fit_data = {}

    def log_append(self,key,point):
        if not self.fit_data.has_key(key):
            self.fit_data[key] = []

        self.fit_data[key].append(point)

    def log_extend(self,key,arr):
        if not self.fit_data.has_key(key):
            self.fit_data[key] = []

        self.fit_data[key].extend(arr)

    def calc_lines(self):
        ref_slope_neg = 0
        ref_slope_pos = 0

        for i in range(self.mean_derivative.shape[0]):
            neg_sh = self.mean_derivative[i,1] * self.mean_derivative[ref_slope_neg,1]
            pos_sh = self.mean_derivative[i,2] * self.mean_derivative[ref_slope_pos,2]

            if True: # abs(neg_sh) < 1 and neg_sh < -0.1:
                self.log_append('calc_neg_mean_switch_hist',neg_sh)
            if True: #  abs(pos_sh) < 1 and pos_sh < -0.1:
                self.log_append('calc_pos_mean_switch_hist',pos_sh)

            self.log_append('calc_neg_derivative',self.mean_derivative[i,1])
            self.log_append('calc_pos_derivative',self.mean_derivative[i,2])


            neg_stds = abs(self.mean_derivative[i,1] - self.mean_derivative_mean[1])/self.mean_derivative_std[1]
            pos_stds = abs(self.mean_derivative[i,2] - self.mean_derivative_mean[2])/self.mean_derivative_std[2]

            self.log_append('calc_neg_stds',[self.mean_derivative[i,0],neg_stds])
            self.log_append('calc_pos_stds',[self.mean_derivative[i,0],pos_stds])

            if neg_stds > 1 or i == self.mean_derivative.shape[0]-1:
                self.neg_lines.append(array([[self.mean[ref_slope_neg,0],self.mean[ref_slope_neg,1],self.std[ref_slope_neg,1]],[self.mean[i,0],self.mean[i,1],self.std[i,1]]]))
                ref_slope_neg = i+1

            if pos_stds > 1 or i == self.mean_derivative.shape[0]-1:
                self.pos_lines.append(array([[self.mean[ref_slope_pos,0],self.mean[ref_slope_pos,2],self.std[ref_slope_pos,2]],[self.mean[i,0],self.mean[i,2],self.std[i,2]]]))
                ref_slope_pos = i+1

    def match_entity(self,neg_l,pos_l):
        d = list(neg_l);
        d.extend(list(pos_l));
        d = array(d)

        ans = polyfit(d[:,0],d[:,1],1,full=True)

        if len(ans[1])==0:
            return None

        return (ans[1][0],self.merged_line(neg_l,pos_l))

    def merged_line(self,neg_l,pos_l):
        d = list(neg_l);
        d.extend(list(pos_l));
        d = array(d)

        mina = d[:,0].argmin()
        maxa = d[:,0].argmax()

        p1 = d[mina,:]
        p2 = d[maxa,:]

        return array([p1,p2])

    def merge_lines(self):
        match_qualities = []
        match_lines = []
        match_indices = []

        for n in range(len(self.neg_lines)):
            for p in range(len(self.pos_lines)):
                neg_l = self.neg_lines[n]
                pos_l = self.pos_lines[p]
                me = self.match_entity(neg_l,pos_l)
                if me == None:
                    continue
                match_qualities.append(me[0])
                match_lines.append(me[1])
                match_indices.append((n,p))

        match_qualities = array(match_qualities)
        match_qualities_mean = match_qualities.mean()

        self.log_extend('match_qualities',match_qualities)

        order = match_qualities.argsort()
        sorted_match_qualities = match_qualities.take(order)
        gapsizes = sorted_match_qualities[1:]-sorted_match_qualities[:-1]
        meangapsize = gapsizes.mean()
        self.log_extend('gap_sizes',gapsizes)

        used_neg_l = []
        used_pos_l = []

        for i_unordered in range(len(gapsizes)):
            i = order[i_unordered]

            if used_neg_l.count(match_indices[i][0]) or used_pos_l.count(match_indices[i][1]) or match_qualities[i] > match_qualities_mean:
                break;

            self.shared_lines.append(match_lines[i])

            used_neg_l.append(match_indices[i][0])
            used_pos_l.append(match_indices[i][1])

    def fit(self):
        self.calc_mean()
        self.calc_lines()
        self.merge_lines()

        if len(self.shared_lines) > 100:
            print "Data noisy"
            self.shared_lines = []

        # self.lines = array(self.lines)

    def mode(self,array,bins=100):
        ans = histogram(array,bins)

        max = ans[0].argmax()

        return ans[1][max]+0.5*(ans[1][1]-ans[1][0])

    def calc_mean(self):
        last_flux = self.s_flux[0]
        last_index = 0

        self.actual_mean = []
        self.mean = []
        self.std = []

        for i in range(len(self.s_flux)/self.stats):
            tneg = self.s_negative_time[i*self.stats:i*self.stats+self.stats]
            meanneg = tneg.mean()
            #meanneg = self.mode(tneg)
            stdneg = tneg.std()

            tpos = self.s_positive_time[i*self.stats:i*self.stats+self.stats]
            meanpos = tpos.mean()
            #meanpos = self.mode(tpos)
            stdpos = tpos.std()

            flux = self.s_flux[i*self.stats]

            self.actual_mean.append([flux,tneg.mean(),tpos.mean()])
            self.mean.append([flux,meanneg,meanpos])
            self.std.append([flux,stdneg,stdpos])

        self.actual_mean = array(self.actual_mean);
        self.mean = array(self.mean)
        self.std = array(self.std)

        self.mean_derivative = self.mean[1:,:] - self.mean[:-1,]
        self.mean_derivative[:,0] = 0.5*(self.mean[1:,0] + self.mean[:-1,0])

        self.meansort = self.mean.argsort(axis=0)
        self.median_derivative = self.mean_derivative[self.meansort[len(self.meansort)/2,0],1]

        self.mean_derivative_mean = self.mean_derivative.mean(axis=0)
        self.mean_derivative_std = self.mean_derivative.std(axis=0)

if __name__ == "__main__":

    cxn = labrad.connect()
    data_vault = cxn.data_vault

    paths = []

    paths.append((['','Markus','Experiments','2008/04/08 - Trigger Tests'],11))
    paths.append((['','Haohua','080403','r7c6','080407'],7))
    paths.append((['','Markus','Experiments','2008/04/06 - Check Qubits'],39))
    paths.append((['','Markus','Experiments','06/14/2008 - Daniel Settling'],1))
    paths.append((['','Markus','Experiments','2008/04/07 - More Qubit Checks'],18))
    paths.append((['','Markus','Experiments','2008/04/07 - More Qubit Checks'],17))
    paths.append((['','Markus','Experiments','2008/04/07 - More Qubit Checks'],9))
    paths.append((['','Markus','Experiments','2008/04/07 - More Qubit Checks'],13))
    paths.append((['','Markus','Experiments','2008/04/07 - More Qubit Checks'],15))

    paths = dv_search(data_vault,re.compile(".*Squid.*Steps.*"),['','Markus','Experiments','2008/05/10 - Check Qubits (Daniel)'])
    paths = dv_search(data_vault,re.compile(".*Squid.*Steps.*"),['','Markus','Test','Basic Experiments'])

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
        try:
            print "======================================================"
            print "++++++++++++++++++++++++++++++++++++++++++++++++++++++"
            print "||||||||||||||||||||||||||||||||||||||||||||||||||||||"
            print path

            dv = cxn.data_vault.packet()
            dv.cd(path[0])
            dv.open(path[1])
            dv.get(key='data')

            dv.get_parameter('Stats',key='stats')
            try:
                ans = dv.send()
            except:
                print "error during get.  Recovering..."
                continue

            data = array([[]])
            data = ans.data.asarray

            print data.shape

            if data.shape[1]!=3 or data.shape[0]<=5 or data[:,1].std()<1e-9:
                print "Skipping because of bad shape: ",data.shape
                continue

            print "New Data Set:",n
            print "Mean: ",data[:,1].mean(),",",data[:,2].mean()
            print "Std:  ",data[:,1].std(),",",data[:,2].std()

            fitobj = squid_fit(data[:,0],data[:,1],data[:,2],ans.stats)
            fitobj.fit()

            print "Done fitting."

            minNeg = data[:,1].min()
            minPos = data[:,2].min()
            maxNeg = data[:,1].max()
            maxPos = data[:,2].max()

            if minNeg<minPos:
                minimum = minNeg
            else:
                minimum = minPos

            if maxNeg<maxPos:
                maximum = maxPos
            else:
                maximum = maxNeg;

            colors = ["c",(0.5,0.5,1),(1,0.8,0.8,1),(0.5,1,0.5,1),"c"]

            subplot(221)
            cla()
            title('Squid steps')
            grid()

            for i in range(1,data.shape[1]):
                plot(data[:,0],data[:,i],color=colors[i],ls='',marker='.',alpha=0.02)

            plot(fitobj.mean[:,0],fitobj.mean[:,1],color=(0.5,0.5,1,1),ls="--")
            plot(fitobj.mean[:,0],fitobj.mean[:,2],color=(1,0.5,0.5,1),ls="--")

            errorbar(fitobj.actual_mean[:,0],fitobj.actual_mean[:,1],yerr=fitobj.std[:,1],color=(0.5,0.5,1,1),mfc=(0.5,0.5,1), mec=(0.5,0.5,1), ms=10, mew=1)
            errorbar(fitobj.actual_mean[:,0],fitobj.actual_mean[:,2],yerr=fitobj.std[:,2],color=(1,0.5,0.5,1),mfc=(1,0.5,0.5), mec=(1,0.5,0.5), ms=10, mew=1)

            for l in fitobj.neg_lines:
                plot(l[:,0],l[:,1],"b-")
            for l in fitobj.pos_lines:
                plot(l[:,0],l[:,1],"r-")
            for l in fitobj.shared_lines:
                plot(l[:,0],l[:,1],"g-",alpha=0.3,linewidth=5)

            #title("Squid Steps")

            subplot(223)
            cla()
            title('Stds for slope')
            grid()

            if(fitobj.fit_data.has_key('calc_neg_stds')):
               hd = array(fitobj.fit_data['calc_neg_stds'])
               plot(hd[:,0],hd[:,1],'.',color=(0.4,0.4,1.0),alpha=1)
            if(fitobj.fit_data.has_key('calc_pos_stds')):
               hd = array(fitobj.fit_data['calc_pos_stds'])
               plot(hd[:,0],hd[:,1],'.',color=(1.0,0.4,0.4),alpha=1)

            subplot(224)
            cla()
            title('Gap Sizes')
            if fitobj.fit_data.has_key('gap_sizes'):
                hd = array(fitobj.fit_data['gap_sizes'])
                plot(range(len(hd)),hd)

            ion()

            subplot(222)
            cla()
            title('Data histograms')

            hist(data[:,1],bins=arange(minimum,maximum,0.1),facecolor=(0.0,0.0,1.0),alpha=0.5)
            hist(data[:,2],bins=arange(minimum,maximum,0.1),facecolor=(1.0,0.0,0.0),alpha=0.5)



            def f(event):
                i = data[:,0].searchsorted(event.xdata);

                subplot(224)
                cla()

                title("Histogram at "+str(data[i,0]))
                hist(data[i:i+ans.stats,1],bins=arange(minimum,maximum,0.4),facecolor=(0.0,0.0,1.0),alpha=0.5)
                hist(data[i:i+ans.stats,2],bins=arange(minimum,maximum,0.4),facecolor=(1.0,0.0,0.0),alpha=0.5)
                show()


            connect("button_press_event",f)

            show()


            raw_input("Hit enter to return")
        except KeyboardInterrupt:
            raise
        except e:
            print "Trigger Exception, traceback info forward to log file."
            traceback.print_exc(sys.stdout)
            continue


    cxn.disconnect()
