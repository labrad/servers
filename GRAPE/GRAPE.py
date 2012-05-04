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
#
# > grape
# This will show a list of all available commands (settings) on the server
#
# > grape.controlZ
# This will show a list of input parameters needs to run controlZ
#
# > grape.controlZ(parameters...)
# Actually run the code.
#
# Definitely need to check that file writing code is correct. Just check online tutorial.

from labrad.server import LabradServer, setting
from labrad import util 

from twisted.internet import defer, reactor
from twisted.internet.defer import returnValue

from pyle.dataking import util as datakingUtil
from pyle import registry

import os

GRAPERunName = 'InterfaceTest'
EXECUTABLE = './UCSB_GRAPE_CZ.sh'+GRAPERunName

CONTROL_PARAMETERS = [('swapBusTime','swapBusTime_1','ns'),('f10', 'f10_1', 'GHz'),('f20', 'f21_1', 'GHz')]
TARGET_PARAMETERS = [('swapBusTime','swapBusTime_1','ns'),('f10', 'f10_2', 'GHz'),('f20', 'f21_1', 'GHz')]
NONQUBIT_PARAMETERS = [('BusFrequency','BusFrequency','GHz'),('GateTime','GateTime','ns'),('Tolerence','Tolerence',''),('Buffer Pixels','Buffer Pixels',''),('Maximum Iterations','Maximum Iterations',''),('SubPixels','SubPixels',''),('Parameter','Parameter',''),('NonLinFlag','NonLinFlag','')]

STRING_PARAMETERS =[('Run Name','Run Name',''),('StartPulse','StartPulse',''),('Filter','Filter',''),('NonLinFile','NonLineFile_1',''),('NonLinFile','NonLineFile_2','')]

# Function to write the input GRAPE needs
def writeParameterFile(path, control, target, nonqubit):
    toWrite = []
    #For each parameter name, get that parameter's value from
    #the qubit dictionary and stick it in a list along with
    #it's GRAPE name and unit. Later the unit will be used to
    #turn LabRAD Values into pure floats in the desired unit.
    for parameter, grapeName, unitTag in CONTROL_PARAMETERS:
        toWrite.append((grapeName, control[parameter], unitTag))
    for parameter, grapeName, unitTage in TARGET_PARAMETERS:
        toWrite.append((grapeName, target[parameter], unitTag))
    for parameter, grapeName, unitTage in NONQUBIT_PARAMETERS:
        toWrite.append((grapeName, nonqubit[parameter], unitTag))
    #for parameter, grapeName, unitTage in SIMULATION_PARAMETERS:
    #    toWrite.append((grapeName, simulation[parameter], unitTag))
    #At this point, toWrite will look like this:
    #[(<GRAPE name>, <value> ie. 5.6MHz, 'GHz'), (similar...)]
    print 'Got to file writing block'
    f = open(path,'w')
    #Start by writting experimental parameters to the file
    for grapeName, value, unitTag in toWrite:
        f.write('<'+grapeName+'>\n')
	f.write('\t')
        f.write(makeWriteable(value, unitTag))
	f.write('\n')
        f.write('</'+grapeName+'>\n')
    f.write('<Stop>')
    f.close
    
def makeWriteable(value, unitTag):
    if unitTag == '':
        return str(value)
    else:
        return str(value[unitTag])
    
class GRAPE(LabradServer):
    """Invokes GRAPE algorithm on the local machine"""
    name = "GRAPE"
    
    @setting(30, qubit0 = '*(sv)', qubit1 = '*(sv)', nonqubit = '*(sv)', returns = '*2v')
    def controlZ(self, c, qubit0, qubit1, nonqubit):
        """Buids GRAPE control z sequence from """
        #Take lists of (name,value) and pack them into python dictionaries
        #for each qubit
        qubit0 = dict(qubit0.aslist)
        qubit1 = dict(qubit1.aslist)
        # Need to set this up so that it writes two files with usage of Hnl or not!
        # Write relevant parameters to file
        os.chdir('/home/daniel/UCSB_CZ/')
        print 'Changed dir'
        writeParameterFile('Run1_InputData.dat', qubit0, qubit1)
        writeParameterFile('Run2_InputData.dat', qubit0, qubit1)
        #Invoke GRAPE
        # os.system(EXECUTABLE)
        # Read GRAPE result from file and parse
        # Get result and turn it into a numpy array
        return np.array([[1,2],[5,6]])
   
    @setting(31, path = 's')
    def cd(self, c, path):
        os.chdir(path)
   
    @setting(32, filename='s')
    def setParameterFileName(self, c, filename):
        c['parameterFileName'] = filename
        
    
    
if __name__=="__main__":
    from labrad import util
    util.runServer(GRAPE())

