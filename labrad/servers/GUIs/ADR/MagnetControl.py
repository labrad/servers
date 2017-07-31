import sys, math

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from twisted.internet.defer import inlineCallbacks

import numpy as np
import matplotlib
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbar
from matplotlib.figure import Figure

UPDATE_PERIOD = 0.2 # seconds

COLORS = ['r', 'g', 'b', 'c', 'm', 'y', 'k', 'Brown', 'Grey', 'OliveDrab']
AXES2 = [5,6,7]
HIDDEN_LINES = [2,4,8]
AXES2 = [3,4,5]

MAX_PLOT_POINTS = 10000
            
SWITCH_TRUE_TEXT = 'Desired Switch State: <font color="red">HEATED</font>'
SWITCH_FALSE_TEXT = 'Desired Switch State: <font color="blue">COOLED</font>'
            
class AppForm(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        self.setWindowTitle('Magnet Control')

        self.create_main_frame()
        self.on_draw()
        
        self.cxn = None
        cxnDef = labrad.connectAsync(name=labrad.util.getNodeName() + ' Magnet Control GUI')
        cxnDef.addCallback(self.set_cxn)
        
        self.updateTimer = QTimer()
        QObject.connect(self.updateTimer, SIGNAL('timeout()'), self.timer_func)
        self.updateDeferred = None
    
    def set_cxn(self, cxn):
        # we've got the connection, save it
        self.cxn = cxn
        self.mag = self.cxn.magnet_controller
        self.populateGrid()
        self.waitingOnLabRAD = False
        self.updateTimer.start(UPDATE_PERIOD * 1000)
    
    def timer_func(self):
        ''' called by the timer '''
        if self.waitingOnLabRAD:
            return
        self.waitingOnLabRAD = True
        p = self.mag.packet()
        p.get_values()
        p.get_status()
        p.get_dataset_name()
        p.persistent_switch()
        p.sensing_mode()
        d = p.send()
        d.addCallback(self.update_callback)
        d.addErrback(self.update_errback)
        if self.plotName[0] != 'None':
            p = self.cxn.data_vault.packet()
            p.variables()
            p.get(1000)
            d2 = p.send()
            d2.addCallback(self.update_plot_callback)
        self.updateDeferred = d
        
    def update_callback(self, response):
        ''' Gets called with the packet response. '''
        for val, label in zip(response.get_values, self.valueLabels):
            if math.isnan(val.value):
                label.setText('-')
            else:
                label.setText('% .4f' % val.value)
        for status, label in zip(response.get_status, self.statusLabels):
            label.setText(status)
        if response.persistent_switch:
            self.switchLabel.setText(SWITCH_TRUE_TEXT)
            self.switchTrueButton.setEnabled(False)
            self.switchFalseButton.setEnabled(True)
        else:
            self.switchLabel.setText(SWITCH_FALSE_TEXT)
            self.switchTrueButton.setEnabled(True)
            self.switchFalseButton.setEnabled(False)
        self.sensingModeBox.setChecked(response.sensing_mode)
        # if we've got a new dataset, open it
        if self.plotName[-1] != response.get_dataset_name[-1]:
            self.plotName = response.get_dataset_name
            p = self.cxn.data_vault.packet()
            p.cd(response.get_dataset_name[:-1])
            p.open(response.get_dataset_name[-1])
            p.send()
            self.plotData = None
            
        self.waitingOnLabRAD = False
        
    def update_errback(self, failure):
        self.waitingOnLabRAD = False
        failure.trap(labrad.types.Error)
        if "DeviceNotSelectedError" in failure.getTraceback():
            self.mag.select_device()
            #print "selecting device"
        else:
            print failure
    
    def update_plot_callback(self, response):
        ''' callback for getting data from data vault.
        response should be a packet response object with response.get == [the data]
        also .variables'''
        if self.plotData is None:
            self.plotData = response.get.asarray
            self.tZero = self.plotData[0,0]
            self.plotData[:,0] = self.plotData[:,0] - self.tZero    # take off the 9 million seconds or whatever
            self.plotData[:,0] /= 60.0 # convert to minutes
            self.plotVars = map(lambda x: '%s [%s]' % (x[1], x[2]), response.variables[1])
            self.plotData = np.delete(self.plotData, HIDDEN_LINES, axis=1)
            HIDDEN_LINES.sort(reverse=True)
            for i in HIDDEN_LINES:
                self.plotVars.pop(i-1)
            self.axes2.set_xlabel("Time (min)")
            self.plotLines = []
            for i in range(1, self.plotData.shape[1]):
                ax = self.axes
                if i in AXES2:
                    ax = self.axes2
                self.plotLines.append(ax.add_line(matplotlib.lines.Line2D(self.plotData[:,0], self.plotData[:,i],
                                                                         label=self.plotVars[i-1], color=COLORS[i-1])))
            self.axes.autoscale()
            self.axes2.autoscale()
            self.axes.legend(prop={'size': 'x-small'}, loc='upper left')
            self.axes2.legend(prop={'size': 'x-small'}, loc='upper left')
            self.canvas.draw()
        else:
            # update the data we have
            newdata = response.get.asarray
            newdata[:,0] = newdata[:,0] - self.tZero
            newdata[:,0] /= 60.0
            newdata = np.delete(newdata, HIDDEN_LINES, axis=1)
            self.plotData = np.append(self.plotData, newdata, axis=0)
            # trim down if we've got too many
            if self.plotData.shape[0] > MAX_PLOT_POINTS:
                self.plotData = self.plotData[self.plotData.shape[0] - MAX_PLOT_POINTS:, :]
            for i in range(1, newdata.shape[1]):
                self.plotLines[i-1].set_data(self.plotData[:,0], self.plotData[:,i])
            self.axes.set_xlim(xmax=self.plotData[-1,0])
            self.axes2.set_xlim(xmax=self.plotData[-1,0])
            self.canvas.draw()
    
    def on_draw(self):
        """ Redraws the figure
        """
        pass

    def setCurrent(self):
        val, ok = QInputDialog.getText(self, "Change Current", "New current setpoint [A]: ")
        if ok:
            self.mag.current_setpoint(float(val))

    def setVoltageLimit(self):
        val, ok = QInputDialog.getText(self, "Change Voltage Limit", "New voltage limit [V]: ")
        if ok:
            self.mag.voltage_limit(float(val))

    def openSwitch(self):
        self.mag.persistent_switch(True)
    def closeSwitch(self):
        self.mag.persistent_switch(False)
            
    def setSensingMode(self):
        self.mag.sensing_mode(self.sensingModeBox.isChecked())
            
    def create_main_frame(self):
        hbox = QHBoxLayout()
        
        # build up our data grid
        self.grid = GridLayoutFormatted()
        self.grid.setSpacing(4)
        self.statusGrid = GridLayoutFormatted()
        self.statusGrid.setSpacing(4)

        hbox2 = QHBoxLayout()
        self.switchLabel = QLabel("Desired Switch State: [none]")
        self.switchTrueButton = QPushButton("Heated/Open")
        self.switchTrueButton.clicked.connect(self.openSwitch)
        self.switchFalseButton = QPushButton("Cooled/Closed")
        self.switchFalseButton.clicked.connect(self.closeSwitch)
        for x in [self.switchLabel, self.switchTrueButton, self.switchFalseButton]:
            hbox2.addWidget(x)
        self.sensingModeBox = QCheckBox("Sensing Mode")
        self.sensingModeBox.setToolTip("Check this if the supply's sense wires are plugged into the magnet voltage taps.")
        self.sensingModeBox.clicked.connect(self.setSensingMode)
        
        vbox = QVBoxLayout()
        vbox.addLayout(self.grid)
        qf = QFrame()
        qf.setFrameStyle(QFrame.HLine)
        qf.setFrameShadow(QFrame.Raised)
        qf.setLineWidth(2)
        vbox.addWidget(qf)
        vbox.addLayout(self.statusGrid)
        qf = QFrame()
        qf.setFrameStyle(QFrame.HLine)
        qf.setFrameShadow(QFrame.Raised)
        qf.setLineWidth(2)
        vbox.addWidget(qf)
        vbox.addLayout(hbox2)
        vbox.addWidget(self.sensingModeBox)
        vbox.addStretch(1)
        hbox.addLayout(vbox)
        
        self.createPlot()
        plotBox = QVBoxLayout()
        plotBox.addWidget(self.canvas)
        plotBox.addWidget(self.mpl_toolbar)
        hbox.addLayout(plotBox)

        self.main_frame = QWidget()
        self.main_frame.setLayout(hbox)
        self.setCentralWidget(self.main_frame)
        
    def createPlot(self):
        # Create the mpl Figure and FigCanvas objects. 
        # 5x4 inches, 100 dots-per-inch
        #
        self.dpi = 100
        self.fig = Figure((10.0, 4.0), dpi=self.dpi)
        self.canvas = FigureCanvas(self.fig)
        
        # Since we have only one plot, we can use add_axes 
        # instead of add_subplot, but then the subplot
        # configuration tool in the navigation toolbar wouldn't
        # work.
        #
        self.axes = self.fig.add_subplot(211)
        self.axes2 = self.fig.add_subplot(212)
        
        # Create the navigation toolbar, tied to the canvas
        #
        self.mpl_toolbar = NavigationToolbar(self.canvas, None)
        
        self.plotName = ['None']
        self.plotData = None
        
    def populateGrid(self):
        # extract the values we get returned from the description
        self.grid.addWidget(QLabel('Value'), 0, 1, align = Qt.AlignHCenter | Qt.AlignVCenter)
        self.grid.addWidget(QLabel('Setpoint'), 0, 2, align = Qt.AlignHCenter | Qt.AlignVCenter)
        self.valueLabels = []
        setpoints = []
        r = 1
        for v in self.mag.get_values.__doc__.split('\n')[2].split(','):
            if r == 1 or (r == 2 and 'Setpoint' in v):
                vlabel = ClickLabel('-', self.setCurrent)
            elif (r == 4 and not 'Setpoint' in v) or (r == 5 and 'Setpoint' in v):
                vlabel = ClickLabel('-', self.setVoltageLimit)
            else:
                vlabel = QLabel('-')
            self.valueLabels.append(vlabel)
            if 'Setpoint' not in v:
                self.grid.addWidget(QLabel(v.strip()), r, 0, size = 13)
                self.grid.addWidget(vlabel, r, 1, box=True)
                r += 1
            else:
                setpoints.append(r-1)
                self.grid.addWidget(vlabel, r-1, 2, box=True)
        for r1 in range(1, r):
            if r1 not in setpoints:
                self.grid.addWidget(QLabel("N/A"), r1, 2, box=True, size = 13)
        self.grid.setRowStretch(r, 1)                
        # do the same for the status grid
        self.statusGrid.addWidget(QLabel('Status'), 0, 0, colspan=2, align = Qt.AlignHCenter | Qt.AlignVCenter)
        self.statusLabels = []
        r = 1
        for v in self.mag.get_status.__doc__.split('\n')[2].split(','):
            vlabel = QLabel('-')
            self.statusLabels.append(vlabel)
            self.statusGrid.addWidget(QLabel(v.strip()), r, 0, size = 13)
            self.statusGrid.addWidget(vlabel, r, 1, size = 13)
            r += 1
        self.statusGrid.setRowStretch(r, 1)

    #@inlineCallbacks
    def closeEvent(self, closeEvent):
        self.updateTimer.stop()
        self.cxn.disconnect()
        #if self.updateDeferred:
        #    yield self.updateDeferred
                
class GridLayoutFormatted(QGridLayout):
    def addWidget(self, widget, r, c, rowspan=1, colspan=1, **kwargs):
        self.formatCell(widget, **kwargs)
        QGridLayout.addWidget(self, widget, r, c, rowspan, colspan)
        
    def formatCell(self, widget, box = False, align = Qt.AlignRight | Qt.AlignVCenter, size = 16):
        widget.setAlignment(align)
        font = QFont("Courier", size, QFont.Bold)   # Bold is 75 (can go 0 to 99)
        font.setStyleHint(QFont.TypeWriter)
        widget.setFont(font)
#        widget.setFont(QFont("Courer New", size))
#        widget.setSizePolicy(QSizePolicy(0,0))
        if box:
            widget.setFrameStyle(QFrame.Box)
            
class ClickLabel(QLabel):
    def __init__ (self, str, func):
        QLabel.__init__(self, str)
        self.func = func
        
    def mouseReleaseEvent(self, event):
        self.func()

if __name__ == '__main__':        
    app = QApplication(sys.argv)
    import qt4reactor
    qt4reactor.install()
    from twisted.internet import reactor
    import labrad, labrad.util, labrad.types
    form = AppForm()
    form.show()
            
    reactor.runReturn()
    sys.exit(app.exec_()) 
