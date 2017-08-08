import numpy
import math
from math import sqrt

def lorenzian(parameters,x,arguments=None):
    """Returns lorenzian calculated for all values in array x, given
    parameters and arguments"""

    A,gamma,x0,baseline = parameters
    
    if(isinstance(arguments,dict)):
        if arguments.has_key('A'):
            A = arguments['A']
        if arguments.has_key('gamma'):
            gamma = arguments['gamma']
        if arguments.has_key('x0'):
            x0 = arguments['x0']
        if arguments.has_key('x0min') and x0 < arguments['x0min']:
            x0 = arguments['x0min']
            return 100000
        if arguments.has_key('x0max') and x0 > arguments['x0max']:
            x0 = arguments['x0max']
            return 100000
        if arguments.has_key('baseline'):
            baseline = arguments['baseline']
    
    return A/((1+pow((x-x0)/gamma,2)))+baseline

def line(parameters,x,arguments=None):
    m,b = parameters

    return m*x+b;

def gaussian(parameters,x,arguments=None):
    mean,std,area = parameters;
    normalization = (area/(std * sqrt(2*math.pi)))
    if arguments.has_key('amplitude'):
        normalization = arguments['amplitude']
    
    return normalization*numpy.exp(0.5*((x-mean)/std)**2);
    

def residuals(p,y,x,func,args=None):
##    if(args and args.has_key('weights')):
##        return (y-func(p,x,args))*args['weights']
##    else:
        return y - func(p,x,args)

def chi(p,y,x,func,args=None):
    res = y-func(p,x,args)
    mean = (res**2).mean()
    return sqrt(mean)

def smaller(a,b):
    if a<b:
        return a
    else:
        return b

def bigger(a,b):
    if a<b:
        return b
    else:
        return a

def smooth(a,smoothing):
    if(smoothing < 2):
        return a
    
    l = len(a)
    ret=numpy.empty(l)
    for i in range(l):
        start = bigger(0,i-smoothing/2)
        end = smaller(l,start+smoothing)
        ret[i] = a[start:end].mean()
    return ret

    
        
        
