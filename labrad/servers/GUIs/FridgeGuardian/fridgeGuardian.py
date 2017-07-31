# Copyright (C) 2013  Daniel Sank
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

import labrad
from labrad.units import Unit, Value
s = Unit('s')

from PyQt4 import QtCore, QtGui, uic
import sys


POLLING_TIME = 1000 #milliseconds

SERVER_NAME = 'cryo_notifier'

TIMER_NAMES = ['LN2','LHe','Trap']
#Timer names are eg. 'vince:LN2', 'jules:Tra


class FridgeGuardianMainWindow(QtGui.QMainWindow):
    def __init__(self, cxn):
        self.connected = False
        self.cxn = cxn
        super(FridgeGuardianMainWindow, self).__init__()
        uic.loadUi('fridgeGuardian.ui', self)

        self.pollingTimer = QtCore.QTimer()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.show() 
        #The order of these buttons and displays matters, as it must match
        #with TIMER_NAMES in order to properly sort the response from the
        #timer cryo_notifier server
        self.buttons = [self.LN2_button, self.LHe_button, self.Trap_button]
        self.displays = [self.LN2_display, self.LHe_display, self.Trap_display]
        self.counters  = [self.LN2_count, self.LHe_count, self.Trap_count]
        self.dewars = [self.LN2_dewar, self.LHe_dewar, self.Trap_dewar]

        def do_call(f, args):
            return lambda: f(*args)
        for (name, button, dewar) in zip(TIMER_NAMES, self.buttons, self.dewars):
            print('connecting signals for %s (%s, %s)' %( name, button, dewar))
            button.clicked.connect(do_call(self.logFill, (name,)))
            dewar.clicked.connect(do_call(self.newDewar, (name,)))
                                   
        self.cryoLineEdit.editingFinished.connect(self.updateCryoName)
        self.updateCryoName()
        self.pollingTimer.timeout.connect(self.checkTimers)
        self.connect_button.clicked.connect(self.connect)
        
        self.initialize()

        self.show()
    
    def updateCryoName(self):
        """Update names of timers we care about"""
        name = str(self.cryoLineEdit.text())
        self.cryoName = str(name)
        print('cryo name updated to %s'%name)
    
    def initialize(self):
        #Connect to labrad
        self.connect()
        self.pollingTimer.start(POLLING_TIME)
        
    def checkTimers(self):
        if self.connected:
            try:
                timer_data = dict(self.server.query_timers())
                counter_data = dict(self.server.query_counters())
                #data = {'Vince:LN2':15*s, 'Vince:LHe':20*s, 'DR:Trap':0*s}
                self.updateDisplays(timer_data, counter_data)
            except Exception:
                #<indicate connection failure>
                self.connect()
        else:
            #<try to connect>
            #if <successful>:
            #    self.checkTimers()
            print('wanted to check timers but not connect')
        self.pollingTimer.start(POLLING_TIME)

    def updateDisplays(self, timer_data, counter_data):
        for timerName,display,counter in zip(TIMER_NAMES, self.displays, self.counters):
            fullName = '%s:%s'%(self.cryoName, str(timerName))
            count = counter_data.get(fullName, -1)
            counter.display(count)
            time = timer_data.get(fullName, None)
            if time:
                hours = int((time['s'])/3600)
                minutes = int((time['s'] - hours*3600)/60)
                seconds = int(time['s'] - hours*3600 - minutes*60)
                display.display('%d:%02d:%02d' % ( hours, minutes, seconds))
                if time['s']<0:
                    #<do something to indicate fill needed>
                    print('Timer %s has reached zero'%fullName)
            else:
                #<indicate unavailable data>
                print('Timer %s could not be found'%fullName)
    
    def connect(self):
        self.server = self.cxn.servers[SERVER_NAME]
        #<Handle errors etc>
        self.connected = True
    
    def logFill(self, channel):
        print('Resetting timer %s:%s'%(self.cryoName,channel))
        self.server.reset_timer('%s:%s'%(self.cryoName,channel), str(self.fillMessage.toPlainText()))
        self.fillMessage.setText('')
    def newDewar(self, channel):
        print('Resetting counter %s:%s'%(self.cryoName,channel))
        self.server.counter('%s:%s' % (self.cryoName,channel), 0)
        self.fillMessage.append('New %s dewar' % channel)

def main():
    with labrad.connect() as cxn:
        app = QtGui.QApplication(sys.argv)
        w = FridgeGuardianMainWindow(cxn)
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
