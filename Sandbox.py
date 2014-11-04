# Copyright (C) 2007  Daniel Sank
#
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


# CHANGELOG:
#

"""
### BEGIN NODE INFO
[info]
name = Sandbox
version = 1.0
description = Test bed

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from __future__ import with_statement
import sys
import os
import itertools
import struct
import time
import random

import numpy as np

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T
from labrad.server import LabradServer, setting

class SandboxServer(LabradServer):
    """Test bed server
    """
    name = 'Sandbox'
    
    @setting(1, 'check', data='*v[Hz]', returns='*v[Hz]')
    def check(self, c, data):
        print data
        return data

__server__ = SandboxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
