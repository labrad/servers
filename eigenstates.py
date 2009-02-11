# Copyright (C) 2007  Matthew Neeley
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

"""
### BEGIN NODE INFO
[info]
name = Eigenstates
version = 1.0
description = Calculates quantum eigenstates of discretized potentials.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.types import Value
from labrad.server import LabradServer, setting
from labrad.errors import Error

from numpy import diag, sign
from numpy.linalg import eig

class PreampServer(LabradServer):
    name = 'Eigenstates'


    @setting(1, 'Eigenstates', mass=['v'], potential=['*v'], dx=['v'], returns='*(v*v)')
    def eig(self, c, mass, potential, dx):
        """Calculates the eigenstates of a particle of given mass in a discretized potential.
        The eigenstates are returned together with their energy sorted by increasing energy.

        NOTE:
        The mass is specified in units of hbar^2.
        dx specifies the distance along the x axis between consecutive entries in the potential.
        """

        V = diag(potential.asarray)
        m = float(mass)
        dx = float(dx)

        D = (diag((-2,)*len(V)) + diag((1,)*(len(V)-1), 1) 
                                + diag((1,)*(len(V)-1),-1))/dx/dx

        M = V - D/(2*m)

        E, U = eig(M)
        
        l = zip(E, range(len(E)))
        l.sort()
       
        U=U.transpose()
        
        Result=[(E[ind[1]], U[ind[1]]*sign(U[ind[1],0]))  for ind in l]
        return Result




__server__ = PreampServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
