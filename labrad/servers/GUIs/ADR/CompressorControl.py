'''
--- Compressor controller. starts/stops compressor, records compressor data. ---

This GUI does LabRAD + QT + matplotlib "correctly" (or at least one way to do so).
The main point is that it is important to do qt4reactor.install before you import twisted (and labrad).
(See the __main__ section at the bottom.)
'''

import sys, math, time

from PyQt4 import QtCore
from PyQt4 import QtGui

from twisted.internet.defer import inlineCallbacks

import numpy as np
import matplotlib
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbar
from matplotlib.figure import Figure

CP_SERVER = 'cp2800_compressor'
DV_SERVER = 'data_vault'
UPDATE_PERIOD = 1.0
DV_PATH = ['', 'ADR', 'Compressor', 'quaid']

class AppForm(QtGui.QMainWindow):
    def __init__(self, parent=None):
        QtGui.QMainWindow.__init__(self, parent)
        self.setWindowTitle('Compressor Control')
        self.create_main_frame()
        
        self.cxn = None
        cxnDef = labrad.connectAsync(name=labrad.util.getNodeName() + ' Compressor Control GUI')
        cxnDef.addCallback(self.set_cxn)
        
        self.dvName = None
        self.upperLines = [3,4,5,6]
        self.lowerLines = [7]
        self.upperLabels = ['Water In', 'Water Out', 'Helium', 'Oil']
        
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.timeout.connect(self.timer_func)
        self.updateDeferred = None
    
    def set_cxn(self, cxn):
        # we've got the connection, save it
        self.cxn = cxn
        self.waitingOnLabRAD = False
        self.updateTimer.start(UPDATE_PERIOD * 1000)
        
    def timer_func(self):
        ''' called when the timer fires '''
        if self.waitingOnLabRAD:
            return
        self.waitingOnLabRAD = True
        if not CP_SERVER in self.cxn.servers:
            self.status_label.setText("Compressor Server not found!")
            self.waitingOnLabRAD = False
            return
        p = self.cxn.servers[CP_SERVER].packet()
        p.status()
        p.motor_current()
        p.temperatures()
        p.pressures()
        d = p.send()
        d.addCallback(self.update_callback)
        d.addErrback(self.update_errback)
        self.status_label.setText("Packet sent...")
        
    def update_callback(self, response):
        self.status_label.setText("Response received.")
        if response.status:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.cpRunning_label.setText('<span style="font-size:16pt; font-weight:600; color:#00aa00;">COMPRESSOR RUNNING</span>')
        else:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.cpRunning_label.setText('<span style="font-size:16pt; font-weight:600; color:#aa0000;">COMPRESSOR STOPPED</span>')
        
        thisData = [time.time()] + [(x[0]['torr'])*(1/51.7149326) for x in response.pressures] + [x[0]['degF'] for x in response.temperatures] + [response.motor_current['A']]
        
        # update internal data, plot
        # create plot if necessary
        if self.data is None:
            self.startTime = time.time()
            self.data = np.array([thisData])
            self.plotLines = []
            for i in self.upperLines:
                self.plotLines.append(self.axes.plot([])[0])
            for i in self.lowerLines:
                self.plotLines.append(self.axes2.plot([])[0])
            self.axes.legend(self.upperLabels, bbox_to_anchor=(0, 1, 1, 0), loc=3, borderaxespad=0., ncol=4, mode="expand")
            self.axes.set_ylim(40, 140)
            self.axes2.set_ylim(-5, 75)
        # if not just add data
        else:
            self.data = np.append(self.data, [thisData], axis=0)
        # update lines on plot
        allLines = self.upperLines + self.lowerLines
        for dataIndex, lineIndex in zip(allLines, range(len(allLines))):
            l = self.plotLines[lineIndex]
            l.set_xdata((self.data[:,0] - self.startTime) / 60.0)
            l.set_ydata(self.data[:,dataIndex])
        self.axes.set_xlim(0, (self.data[-1,0] - self.startTime) / 60.0)
        self.axes2.set_xlim(0, (self.data[-1,0] - self.startTime) / 60.0)
        self.canvas.draw()
        
        # post data to data vault
        # check for DV server
        if not DV_SERVER in self.cxn.servers:
            self.dsName_label.setText("No data vault server!")
            return
        p = self.cxn.servers[DV_SERVER].packet()
        # create dataset if necessary 
        if not self.dvName:
            self.dvName = '%s' % (time.strftime("%Y-%m-%d %H:%M"))
            p.cd(DV_PATH, True)
            p.new(self.dvName, ['time [s]'], [
                   'High Pressure (pressure) [Psi]',
                   'Low Pressure (pressure) [Psi]',
                   'Water In (Temp) [F]',
                   'Water Out (Temp) [F]',
                   'Helium (Temp) [F]',
                   'Compressor Oil (Temp) [F]',
                   'Motor Current (current) [A]',
                   ])
            p.add_parameters(('Start Time (str)', time.strftime("%Y-%m-%d %H:%M")), ('Start Time (int)', time.time()),
                             ('Compressor', str(self.cpName_label.text())))
            self.dsName_label.setText("Dataset Name: <b>" + '/'.join(DV_PATH) + '/' + self.dvName + '</b>')
        # write data
        p.add(thisData)
        p.send()
        self.waitingOnLabRAD = False
        
    def update_errback(self, failure):
        self.waitingOnLabRAD = False
        failure.trap(labrad.types.Error)
        if "DeviceNotSelectedError" in failure.getTraceback():
            p = self.cxn.servers[CP_SERVER].packet()
            p.select_device()
            d = p.send()
            d.addCallback(self.device_selected_callback)
            self.status_label.setText("Selecting device")
        else:
            self.status_label.setText("Error!")
            print failure
            
    def start_button_pushed(self):
        self.cxn.servers[CP_SERVER].start()
        
    def stop_button_pushed(self):
        self.cxn.servers[CP_SERVER].start()
            
    def device_selected_callback(self, response):
        self.cpName_label.setText('Connection: <b>' + response.select_device + '</b>')
            
    def create_main_frame(self):
        outerVBox = QtGui.QVBoxLayout()
        self.status_label = QtGui.QLabel("Status")
        self.cpName_label = QtGui.QLabel("[no device]")
        self.cpRunning_label = QtGui.QLabel("<i>unknown</i>")
        self.cpRunning_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        buttonHBox = QtGui.QHBoxLayout()
        self.start_button = QtGui.QPushButton("Start")
        self.stop_button = QtGui.QPushButton("Stop")
        self.start_button.setFixedHeight(40)
        self.stop_button.setFixedHeight(40)
        self.start_button.clicked.connect(self.start_button_pushed)
        self.stop_button.clicked.connect(self.stop_button_pushed)
        buttonHBox.addWidget(self.start_button)
        buttonHBox.addWidget(self.stop_button)
        self.dsName_label = QtGui.QLabel("[no dataset]")
        outerVBox.addWidget(self.status_label)
        outerVBox.addWidget(self.cpName_label)
        outerVBox.addWidget(self.cpRunning_label)
        outerVBox.addLayout(buttonHBox)
        outerVBox.addWidget(self.dsName_label)
        
        self.create_plot()
        plotBox = QtGui.QVBoxLayout()
        plotBox.addWidget(self.canvas)
        plotBox.addWidget(self.mpl_toolbar)
        outerVBox.addLayout(plotBox)
        
        self.main_frame = QtGui.QWidget()
        self.main_frame.setLayout(outerVBox)
        self.setCentralWidget(self.main_frame)
        
    def create_plot(self):
        self.fig = Figure((10.0, 7.0), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        self.axes = self.fig.add_subplot(211)
        self.axes.xaxis.set_visible(False)
        self.axes.yaxis.set_ticks_position('right')
        self.axes.set_ylabel("Temperature [F]")
        self.axes.autoscale(True, axis='y')
        self.axes2 = self.fig.add_subplot(212)
        self.axes2.yaxis.set_ticks_position('right')
        self.axes2.set_xlabel("Time [min]")
        self.axes2.set_ylabel("Motor Current [A]")
        self.axes.autoscale(True, axis='y')
        self.mpl_toolbar = NavigationToolbar(self.canvas, None)
        self.data = None
        
if __name__ == '__main__':        
    app = QtGui.QApplication(sys.argv)
    import qt4reactor
    qt4reactor.install()
    from twisted.internet import reactor
    import labrad, labrad.util, labrad.types
    form = AppForm()
    form.show()
            
    reactor.runReturn()
    sys.exit(app.exec_())
    