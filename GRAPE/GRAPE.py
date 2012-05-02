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

from labrad.server import LabradServer, setting
from labrad import util 

from twisted.internet import defer, reactor
from twisted.internet.defer import returnValue

import os


CONTROL_PARAMETERS = {}

TARGET_PARAMETERS = {}

def writeParameterFile(path, control, target):
    toWrite = []
    for parameter, alias, unitTag in CONTROL_PARAMETERS:
        toWrite.append((alias, control[parameter], unitTag))
    for parameter, alias, unitTage in TARGET_PARAMETERS:
        toWrite.append((alias, target[parameter], unitTag))
    f = #<open file for writing>
    for alias, value, unitTag in toWrite:
        f.write('<'+alias+'>')
        f.write(makeWriteable(value, unitTag))
        f.write('</'+alias+'>')
    f.close
    
def makeWriteable(value, unitTag):
    if unitTag == '':
        return str(value)
    else:
        return str(value[unitTag])
    
class GRAPE(LabradServer):
    """Invokes GRAPE algorithm on the local machine"""
    name = "GRAPE"
    
    @setting(20, session = '*s', returns = '')
    def session(self, c, session):
        """Get a registry wrapper for the user's session and keep it in this context"""
        cxn = self.client
        reg = registry.RegistryWrapper(cxn, session)
        c['sample'] = reg        
        
    @setting(30, controlIdx = 'i', targetIdx = 'i', returns = '*2v')
    def controlZ(self, c, controlIdx, targetIdx):
        """Buids GRAPE control z sequence from """
        cxn = self.client
        sample, qubits = pyle.dataking.util.loadQubits(c['sample'])
        control = qubits[controlIdx]
        target = qubits[targetIdx]
        #Write relevant parameters to file
        writeParameterFile(c['parameterFilename'], control, target)
        #Invoke GRAPE
        os.system(<run GRAPE>)
        #Read GRAPE result from file and parse
        #Return result
        return np.array([[0,0],[0,0]])
    
    @setting(31, path = 's')
    def cd(self, c, path):
        os.chdir(path)
    
    @setting(32, filename='s')
    def setParameterFileName(self, c, filename):
        c['parameterFileName'] = filename
        
    
    
if __name__=="__main__":
    from labrad import util
    util.runServer(GRAPE())

