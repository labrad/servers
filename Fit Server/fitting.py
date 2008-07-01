import numpy
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

def residuals(p,y,x,func,args=None):
##    if(args and args.has_key('weights')):
##        return (y-func(p,x,args))*args['weights']
##    else:
        return y - func(p,x,args)

def chi(p,y,x,func,args=None):
    res = y-func(p,x,args)
    mean = (res**2).mean()
    return sqrt(mean)
    
