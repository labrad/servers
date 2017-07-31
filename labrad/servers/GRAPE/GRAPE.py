# Copyright (C) 2012 Daniel Sank
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

#CHANGELOG
#
# 2012 April 29
# Created

#NOTES FOR DANIEL E.
#
# > import labrad
# > cxn = labrad.connect()
# > grape = cxn.grape
# > from labrad.units import Value
#
# > grape
# This will show a list of all available commands (settings) on the server
#
# > grape.controlZ
# This will show a list of input parameters needs to run controlZ
#
# > path = ['','Daniel','Benchmarking','w110427A','r4c9','120504']
# > grape.session(path)
# #Define control parameters
# > grape.set_control_z_parameters(Value(40.0,'ns'), ..., ..., ...)
# > result = grape.controlz(index1, index2)

import os

import numpy as np

from labrad.units import Value
from labrad.server import LabradServer, setting
from labrad import util 

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

KEYS = ['swapTimeBus', 'f10', 'f21']

GRAPERunName = 'InterfaceTest'
EXECUTABLE = './UCSB_GRAPE_CZ.sh'

#CONTROL_PARAMETERS = [('swapBusTime','swapBusTime_1','ns'),('f10', 'f10_1', 'GHz'),('f20', 'f21_1', 'GHz')]
#TARGET_PARAMETERS = [('swapBusTime','swapBusTime_1','ns'),('f10', 'f10_2', 'GHz'),('f20', 'f21_1', 'GHz')]
#NONQUBIT_PARAMETERS = [('BusFrequency','BusFrequency','GHz'),('GateTime','GateTime','ns'),('Tolerence','Tolerence',''),('Buffer Pixels','Buffer Pixels',''),('Maximum Iterations','Maximum Iterations',''),('SubPixels','SubPixels',''),('Parameter','Parameter',''),('NonLinFlag','NonLinFlag','')]

STRING_PARAMETERS =[('Run Name','Run Name',''),('StartPulse','StartPulse',''),('Filter','Filter',''),('NonLinFile','NonLineFile_1',''),('NonLinFile','NonLineFile_2','')]

# Function to write the input GRAPE needs
def writeParameterFile_1(path, RunNameString, qubit1, qubit2, nonqubit):
    toWrite = qubit1.items() + qubit2.items() + nonqubit.items()
    
    f = open(path,'w')
    #Start by writting experimental parameters to the file
    for key, value in toWrite:
        f.write('<'+key+'>\n')
        f.write('\t')
        f.write(makeWriteable(value))
        f.write('\n')
        f.write('</'+key+'>\n')
    f.write('<Run Name>\n')
    f.write('\t'+RunNameString+'_1\n')
    f.write('</Run Name>\n')
    f.write('<NonLinFlag>\n')
    f.write('\t0\n')
    f.write('</NonLinFlag>\n')
    f.write('<StartPulse>\n')
    f.write('\tDefault\n')
    f.write('</StartPulse>\n')
    f.write('<Filter>\n')
    f.write('\tVoid\n')
    f.write('</Filter>\n')
    f.write('<Stop>\n')
    f.close()
        
# Function to write the input GRAPE needs
def writeParameterFile_2(path, RunNameString, qubit1, qubit2, nonqubit):
    toWrite = qubit1.items() + qubit2.items() + nonqubit.items()
    
    f = open(path,'w')
    #Start by writting experimental parameters to the file
    for key, value in toWrite:
        f.write('<'+key+'>\n')
        f.write('\t')
        f.write(makeWriteable(value))
        f.write('\n')
        f.write('</'+key+'>\n')
    f.write('<Run Name>\n')
    f.write('\t'+RunNameString+'_2\n')
    f.write('</Run Name>\n')
    f.write('<NonLinFlag>\n')
    f.write('\t1\n')
    f.write('</NonLinFlag>\n')
    f.write('<StartPulse>\n')
    f.write('\tExternal\n')
    f.write('</StartPulse>\n')
    f.write('<Filter>\n')
    f.write('\tGaussian\n')
    f.write('</Filter>\n')
    f.write('<Stop>\n')
    f.close()


def makeWriteable(value):
    if isinstance(value, Value):
        if value.isCompatible('ns'):
            return str(value['ns'])
        elif value.isCompatible('GHz'):
            return str(value['GHz'])
        else:
            return str(value.value)
    else:
        return str(value)
        
        
class GRAPE(LabradServer):
    """Invokes GRAPE algorithm on the local machine"""
    name = "GRAPE"

    @inlineCallbacks
    def readQubitParameters(self, session, qubit1Idx, qubit2Idx):
        cxn = self.client
        reg = cxn.registry
        yield reg.cd(session)
        config = yield reg.get('config')
        qubitNames = [config[i] for i in [qubit1Idx, qubit2Idx]]
        qubits = []
        for i,name in zip([1,2],qubitNames):
            q = {}
            yield reg.cd(name)
            d = yield reg.dir()
            keys = d[1]
            for key in keys:
                if key in KEYS:
                    val = yield reg.get(key)
                    q[key+'_'+str(i)] = val
                else:
                    continue
            qubits.append(q)
            #Go back to starting directory
            yield reg.cd(session)
        returnValue(qubits)
        
    @setting(30, qubit1Idx = 'i', qubit2Idx = 'i', RunNameString='s', returns = '*2v')
    def controlZ(self, c, qubit1Idx, qubit2Idx, RunNameString):
        """Buids GRAPE control z sequence from """
        #Read qubit values from registry
        qubits = yield self.readQubitParameters(c['session'], qubit1Idx, qubit2Idx)
        qubit1 = qubits[0]
        qubit2 = qubits[1]
        # Need to set this up so that it writes two files with usage of Hnl or not!
        # Write relevant parameters to file
        os.chdir('/home/daniel/UCSB_CZ/')
        writeParameterFile_1('Run1_InputData.dat', RunNameString, qubit1, qubit2, c['cz'])
        writeParameterFile_2('Run2_InputData.dat', RunNameString, qubit1, qubit2, c['cz'])
        #Invoke GRAPE
        os.system(EXECUTABLE+' '+RunNameString)
        # Read GRAPE result from file and parse
        data = np.loadtxt('/home/daniel/UCSB_CZ/Output/'+RunNameString+'_2/controls_final.dat')
        # Get result and turn it into a numpy array
        returnValue(data)
      
    @setting(32, 'Set Parameter Filename', filename='s')
    def setParameterFileName(self, c, filename):
        c['parameterFileName'] = filename
        
    @setting(33, 'Session', session='*s')
    def session(self, c, session):
        c['session'] = session
    
    @setting(35, 'Set control Z Parameters', gateTime='v[ns]',Tolerance='v', numBufPixels='i', MaxIter='i',  numSubPixels='i', targetphase='v', busFreq='v[GHz]', anharmFile0 = 's', anharmFile1 = 's')
    def setCzParameters(self, c, gateTime, Tolerance, numBufPixels, MaxIter, numSubPixels, targetphase, busFreq, anharmFile0, anharmFile1):
        c['cz'] = {

                   'Gate Time':             gateTime,
                   'Tolerance':             Tolerance,
                   'Buffer Pixels':         numBufPixels,
                   'Maximum Iterations':    MaxIter,
                   'SubPixels':             numSubPixels,
                   'Target Phase':          targetphase,
                   'BusFrequency':          busFreq,
                   'NonLineFile_1':         anharmFile0,
                   'NonLineFile_2':         anharmFile1
                   }
    
    
if __name__=="__main__":
    from labrad import util
    util.runServer(GRAPE())

