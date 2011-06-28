import labrad
import numpy as np
from struct import unpack
import matplotlib.pyplot as plt

import SR770.sr770 as sr770
from SR770.sr770 import unpackBinary, scaleLogData

cxn = labrad.connect()
sr = cxn.signal_analyzer_sr770
sr.select_device(0)
gp = cxn.kimble_gpib_bus
gp.address(gp.list_devices()[0])

def semilogy(data,**kw):
    plt.semilogy(data[:,0],data[:,1,],**kw)

def shiftLogData(data,ref):
    scaled = (data*3.0103/512)-114.3914-ref
    return 10**(scaled/20.0)

def dbVToV(data):
    return 10**(data/20)

def getTrace():
    refLevel = int(gp.query('IRNG?\n'))
    span = sr.span()
    linewidth = span/sr770.NUM_POINTS
    bytes = gp.query('SPEB?0\n')
    numeric = unpackBinary(bytes)
    dbVoltsPkPerBin = scaleLogData(numeric,refLevel)
    print 'dbVpk/Bin: ',dbVoltsPkPerBin[-1]
    voltsPkPerBin = 10**(dbVoltsPkPerBin/20.0)
    print 'Vpk/Bin: ',voltsPkPerBin[-1]
    voltsPkPerRtHz = voltsPkPerBin/np.sqrt(linewidth['Hz'])
    print 'Vpk/rtHz: ',voltsPkPerRtHz[-1]
    voltsRmsPerRtHz = voltsPkPerRtHz/np.sqrt(2)
    print 'Vrms/rtHz: ',voltsRmsPerRtHz[-1]
    return voltsRmsPerRtHz
    
def bmh(n,N):
    a0=0.35875
    a1=0.48829
    a2=0.14128
    a3=0.01168
    
    return a0-a1*np.cos(2*np.pi*n/(N-1))+a2*np.cos(4*np.pi*n/(N-1))-a3*np.cos(6*np.pi*n/(N-1))