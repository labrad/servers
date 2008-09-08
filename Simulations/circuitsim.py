from __future__ import with_statement

import numpy as N
from numpy import (array, pi, cos, sin, dot, zeros, eye, diag, bmat, hstack, vstack, linalg)

import scipy as S
from scipy.integrate import odeint
from scipy.optimize import leastsq

from processtools import new_priority

# define constants
h = 6.626e-34
hbar = h/2/pi
elec = 1.6022e-19
phi0 = h/2/elec # flux quantum
phi0bar = phi0/2/pi

class Inductor(object):
    def __init__(self, L, i, j=None, bias=0):
        self.L = L
        self.i = i
        self.j = j
        self.bias = bias
        
    E = property(lambda self: phi0bar**2/self.L/2)

    def phase(self, c):
        if self.j is None:
            return c.d[:,self.i] - self.bias
        return c.d[:,self.i] - c.d[:,self.j] - self.bias
        
    def energy(self, c):
        return self.E * self.phase(c)**2
        
    def current(self, c):
        return phi0bar * self.phase(c) / self.L
        
class Mutual(object):
    def __init__(self, M, Lij, Lkl, i, k, j=None, l=None):
        self.M = M
        self.Lij = Lij
        self.Lkl = Lkl
        self.i = i
        self.j = j
        self.k = k
        self.l = l
        
    E = property(lambda self: phi0bar**2*self.M/self.Lij/self.Lkl)
    
    def energy(self, c):
        if self.j is None:
            d0 = c.d[:,self.i]
        else:
            d0 = c.d[:,self.i] - c.d[:,self.j]
        if self.l is None:
            d1 = c.d[:,self.k]
        else:
            d1 = c.d[:,self.k] - c.d[:,self.l]
        return self.E * d0 * d1
        
class Capacitor(object):
    def __init__(self, C, i, j=None):
        self.C = C
        self.i = i
        self.j = j
    
    E = property(lambda self: phi0bar**2*self.C/2)

    def phase(self, c):
        if self.j is None:
            return c.d[:,self.i]
        return c.d[:,self.i] - c.d[:,self.j]

    def dphase(self, c):
        if self.j is None:
            return c.dd[:,self.i]
        return c.dd[:,self.i] - c.dd[:,self.j]

    def ddphase(self, c):
        if self.j is None:
            return c.ddd[:,self.i]
        return c.ddd[:,self.i] - c.ddd[:,self.j]

    def energy(self, c):
        return self.E * self.dphase(c)**2
    
    def current(self, c):
        return phi0bar * self.C * self.ddphase(c)

class Junction(object):
    def __init__(self, I0, i, j=None):
        self.I0 = I0
        self.i = i
        self.j = j
        
    E = property(lambda self: phi0bar*self.I0)
    
    def phase(self, c):
        if self.j is None:
            return c.d[:,self.i]
        return c.d[:,self.i] - c.d[:,self.j]
    
    def energy(self, c):
        return -self.E * cos(self.phase(c))

    def current(self, c):
        return self.I0 * sin(self.phase(c))

class Resistor(object):
    def __init__(self, R, i, j=None):
        self.R = R
        self.i = i
        self.j = j
        
    E = property(lambda self: phi0bar**2/self.R/2)
    
    def phase(self, c):
        if self.j is None:
            return c.d[:,self.i]
        return c.d[:,self.i] - c.d[:,self.j]

    def dphase(self, c):
        if self.j is None:
            return c.dd[:,self.i]
        return c.dd[:,self.i] - c.dd[:,self.j]
    
    def energy(self, c):
        return 0

    def current(self, c):
        return phi0bar * self.dphase(c) / self.R

class CurrentBias(object):
    def __init__(self, I, i):
        self.I = I
        self.i = i
        
    E = property(lambda self: phi0bar*self.I)
        
    def phase(self, c):
        return c.d[:,self.i]
    
    def energy(self, c):
        return 0

class Circuit(object):
    def __init__(self, N, **elements):
        self.N = N
        self.elements = elements
        
    def __setitem__(self, key, value):
        self.elements[key] = value
        
    def __getitem__(self, key):
        return self.elements[key]
        
    def _createMatrices(self):
        N = self.N
        self.A = zeros((N, N))
        self.B = zeros((N, N))
        self.C = zeros(N)
        self.D = zeros((N, N))
        self.E = zeros(N)
        self.F = zeros((N, N))
        
        _add_funcs = {
            Capacitor: self._add_capacitor,
            Inductor: self._add_inductor,
            Mutual: self._add_mutual,
            Junction: self._add_junction,
            Resistor: self._add_resistor,
            CurrentBias: self._add_current_bias}
        
        for e in self.elements.values():
            _add_funcs[type(e)](e)
        
    def _add_capacitor(self, e):
        E, i, j = e.E, e.i, e.j
        if j is None:
            self.A[i,i] += E
        else:
            self.A[i,i] += E
            self.A[i,j] -= E
            self.A[j,i] -= E
            self.A[j,j] += E
        
    def _add_inductor(self, e):
        E, i, j, bias = e.E, e.i, e.j, e.bias
        if j is None:
            self.B[i,i] += E
            self.C[i] -= 2*E*bias
        else:
            self.B[i,i] += E
            self.B[i,j] -= E
            self.B[j,i] -= E
            self.B[j,j] += E
            self.C[i] -= 2*E*bias
            self.C[j] += 2*E*bias
        
    def _add_mutual(self, e):
        E, i, j, k, l = e.E, e.i, e.j, e.k, e.l
        if (j is None) and (l is None):
            self.B[i,k] -= E
        elif j is None:
            self.B[i,k] -= E
            self.B[i,l] += E
        elif l is None:
            self.B[i,k] -= E
            self.B[j,k] += E
        else:
            self.B[i,k] -= E
            self.B[i,l] += E
            self.B[j,k] += E
            self.B[j,l] -= E

    def _add_junction(self, e):
        E, i, j = e.E, e.i, e.j
        if j is None:
            self.E[i] += E
        else:
            self.D[i,j] += E
        
    def _add_resistor(self, e):
        E, i, j = e.E, e.i, e.j
        if j is None:
            self.F[i,i] += E
        else:
            self.F[i,j] += E
        
    def _add_current_bias(self, b):
        E, i = b.E, b.i
        self.C[i] -= E
        
    @property
    def _dfunc(self):
        N = self.N
        
        self._createMatrices()
        
        Abar = self.A + self.A.T
        Bbar = self.B + self.B.T
        Dbar = self.D + self.D.T
        Fbar = self.F + self.F.T
        Ainv = linalg.inv(Abar)
        
        A = array(bmat([[zeros((N,N)), eye(N)],
                        [-dot(Ainv, Bbar), -dot(Ainv, Fbar)]]))

        B = array(bmat([[zeros((N,N)), zeros((N,N))],
                        [-dot(Ainv, diag(self.E)), zeros((N,N))]]))

        C = array(bmat([[zeros((N,N)), zeros((N,N))],
                        [-dot(Ainv, Dbar), zeros((N,N))]]))

        D = hstack((zeros(N), -dot(Ainv, self.C)))

        def diffMat(y):
            yy = vstack((y,)*N)
            return yy.T - yy
        
        return lambda y, t: dot(A, y) + dot(B, sin(y)) + D
    
    def deriv(self, d, dd=None, t=0):
        if dd is None:
            dd = zeros(self.N)
        y = hstack((d, dd))
        return self._dfunc(y, t)
        
    def simulate(self, T, d0, dd0=None, hmax=1e-12, **opts):
        with new_priority():
            if dd0 is None:
                dd0 = zeros(self.N)
            y0 = hstack((d0, dd0))
            self.Y, self.ode_info = odeint(self._dfunc, y0, T, hmax=hmax, full_output=True, **opts)
            
    def energy(self):
        return sum(e.energy(self) for e in self.elements.values())
    
    @property
    def d(self):
        return self.Y[:,:self.N]
    
    @property
    def dd(self):
        return self.Y[:,self.N:]
    
    @property
    def ddd(self):
        return array([self._dfunc(y)[self.N:] for y in self.Y])
