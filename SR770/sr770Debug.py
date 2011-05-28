import labrad
import numpy as np
from struct import unpack
import matplotlib.pyplot as plt

cxn = labrad.connect()
sr = cxn.signal_analyzer_sr770
sr.select_device(0)
gp = cxn.kimble_gpib_bus
gp.address(gp.list_devices()[0])

def getTrace():
    bytes = gp.query('SPEB?0\n')
    numeric = np.array(unpack('h'*400,bytes))
    return numeric

def scaleTraceLog(trace):
    scaled = (trace*3.0103/512.0)-114.3914
    return scaled
