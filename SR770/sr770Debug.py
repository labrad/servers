import labrad
import numpy as np
from struct import unpack
import matplotlib.pyplot as plt

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
