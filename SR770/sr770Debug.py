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
