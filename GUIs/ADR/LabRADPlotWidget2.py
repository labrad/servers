import os, sys, time

import PyQt4.Qt as Qt
import PyQt4.QtCore as QtCore

from twisted.internet.defer import inlineCallbacks, returnValue

import numpy as np, matplotlib as mp, matplotlib.pyplot as plt
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

UPDATE_PERIOD = 0.2     # (in seconds)
COLORS = ['red', 'green', 'blue', 'cyan', 'magenta', 'goldenrod', 'black', 'Brown', 'Grey', 'OliveDrab']
MAX_POINTS = 10000

# A Qt Widget wrapper with some added functionality for selecting parts of a dataset		
class LabRADPlotWidget2(Qt.QWidget):

    def __init__(self, parent, cxn=None, path=[], dataset=None, toolbar=True, timer=None, settings={}):
        """
        A Qt widget that plots a labrad dataset, using Matplotlib.
        """
        # run qwidget init
        Qt.QWidget.__init__(self, parent)
        # create the qt basics
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        if toolbar:
            self.toolbar = NavigationToolbar(self.canvas, None)
        else:
            self.toolbar = None
        self.layout = Qt.QVBoxLayout()
        self.layout.addWidget(self.canvas)
        if self.toolbar:
            self.layout.addWidget(self.toolbar)
        self.setLayout(self.layout)
        self.groupBoxLayout = Qt.QHBoxLayout()
        self.layout.addLayout(self.groupBoxLayout)
        self.makeOptionsBox()
        self.groupBoxes = []
        self.settings = settings
        # matplotlib variables
        self.rebuildPlot = False
        self.subplots = []
        self.lines = []
        # labrad variables
        self.path = path
        self.dataset = dataset
        # start the labrad connection
        if cxn is None:
            import labrad
            cxnDef = labrad.connectAsync(name=labrad.util.getNodeName() + ' Plot Widget')
            cxnDef.addCallback(self.setCxn)
            self.cxn = None
        else:
            self.setCxn(cxn)
        # give us a timer
        if timer is None:
            self.updateTimer = Qt.QTimer()
            self.updateTimer.timeout.connect(self.timerFunc)
            self.waitingOnLabrad=True
            self.updateTimer.start(UPDATE_PERIOD * 1000)
        else:
            self.updateTimer = timer
            self.updateTimer.timeout.connect(self.timerFunc)
            self.waitinOnLabrad=True
        
    def makeOptionsBox(self):
        vl = Qt.QVBoxLayout()
        self.rescaleCB = Qt.QCheckBox("Autoscale Y-Axis")
        self.rescaleCB.setChecked(True)
        
        vl.addWidget(self.rescaleCB)
        self.rescaleXCB = Qt.QCheckBox("Autoscale X-Axis")
        self.rescaleXCB.setChecked(True)
        
        vl.addWidget(self.rescaleXCB)
        l = Qt.QLabel("Minutes to Display")
        self.minutesToDisplayEdit = Qt.QLineEdit()
        hl = Qt.QHBoxLayout()
        hl.addWidget(l); hl.addWidget(self.minutesToDisplayEdit); vl.addLayout(hl)
        
        self.tempUnitsCB = Qt.QCheckBox("Temperature in F")
        self.tempUnitsCB.setChecked(False)
        vl.addWidget(self.tempUnitsCB)

        self.hideUncheckedCB = Qt.QCheckBox("Hide unchecked")
        self.hideUncheckedCB.setChecked(False)
        self.hideUncheckedCB.toggled.connect(self.hideUncheckedCallback)
        vl.addWidget(self.hideUncheckedCB)
        
        optGB = Qt.QGroupBox("Options")
        optGB.setCheckable(False)
        optGB.setLayout(vl)
        optGB.setSizePolicy(Qt.QSizePolicy.Fixed, Qt.QSizePolicy.Fixed)
        self.groupBoxLayout.addWidget(optGB, 0, QtCore.Qt.AlignTop)

    def hideUncheckedCallback(self, toggled):
        if toggled:
            for cb in self.checkBoxes:
                if not cb.isChecked():
                    cb.setVisible(False)
        else:
            for cb in self.checkBoxes:
                cb.setVisible(True)
        
    def setCxn(self, cxn):
        self.cxn = cxn
        if self.dataset:
            self.loadDataset()
        self.waitingOnLabrad=False
        
    def setDataset(self, path=[], dataset=None):
        if path:
            self.path = path
        if dataset:
            self.dataset = dataset
        self.loadDataset()
        
    def getDataset(self):
        return self.dataset
        
    def loadDataset(self):
        p = self.cxn.data_vault.packet()
        p.cd(self.path)
        p.dir()
        d = p.send()
        d.addCallback(self.loadDatasetCallback)
        
    def loadDatasetCallback(self, response):
        dsList = response.dir[1]
        if type(self.dataset) == str and not self.dataset in dsList:
            for ds in dsList:
                if self.dataset in ds:
                    self.dataset = ds
                    break
            else:   # note this else is for the for loop, not the if statement
                self.dataset = None
                print "Dataset %s not found!" % self.dataset
        p = self.cxn.data_vault.packet()
        p.open(self.dataset)
        p.send()
        self.rebuildPlot = True
        
    def timerFunc(self):
        if self.waitingOnLabrad:
            return
        if not self.dataset:
            return
        p = self.cxn.data_vault.packet()
        if self.rebuildPlot:
            p.variables()
        p.get(1000)
        d = p.send()
        d.addCallback(self.datavaultCallback)
        
    def datavaultCallback(self, response):
        if self.rebuildPlot and 'variables' not in response.settings:
            return
        elif self.rebuildPlot:
            for plot in self.subplots:
                self.figure.delaxes(plot)
            self.plots = []
            self.lines = []
            # list of legends
            self.plotLegends = list(set([x[0] for x in response.variables[1]]))
            # dict of lists of labels, where plotLabels[legend] = [list of labels for this legend]
            self.plotLabels = dict(zip(self.plotLegends, [[] for i in range(len(self.plotLegends))]))
            # dict of lists of units, as above
            self.plotUnits = dict(zip(self.plotLegends, [[] for i in range(len(self.plotLegends))]))
            # dict of lists of indices
            self.plotIndices = dict(zip(self.plotLegends, [[] for i in range(len(self.plotLegends))]))
            i = 0
            for legend, label, unit in response.variables[1]:
                i += 1
                self.plotLabels[legend].append(label)
                self.plotUnits[legend].append(unit)
                self.plotIndices[legend].append(i)
            # list of plots
            for i in range(len(self.plotLegends)):
                if i == 0:
                    self.plots.append(self.figure.add_subplot(len(self.plotLegends), 1, i))
                else:
                    self.plots.append(self.figure.add_subplot(len(self.plotLegends), 1, i, sharex=self.plots[0]))
                self.plots[i].set_ylabel(self.plotLegends[i])
                plt.setp(self.plots[i].get_xticklabels(), visible=False)
            self.plotData = response.get
            if 'xAxisIsTime' in self.settings.keys() and self.settings['xAxisIsTime']:
                self.plotT0 = self.plotData[0,0]
                self.plotData[:,0] -= self.plotT0
                self.plotData[:,0] /= 60.0
                self.xlabel = "Time [min] since %s" % time.strftime('%Y-%b-%d %H:%M', time.localtime(self.plotT0))
            else:
                self.xlabel = '%s [%s]' % response.variables[0][0]
            # create the lines
            for i in range(1, self.plotData.shape[1]):
                plotNum = self.plotLegends.index(response.variables[1][i-1][0])
                self.lines.append(self.plots[plotNum].add_line(mp.lines.Line2D(self.plotData[:,0], self.plotData[:,i],
                        label='%s [%s]' % response.variables[1][i-1][1:], color = COLORS[(i-1) % len(COLORS)],
                        marker='o', linestyle='-')))
            for plot in self.plots:
                #plot.legend(prop={'size': 'x-small'}, loc='upper left')
                plot.autoscale()
            self.plots[-1].set_xlabel(self.xlabel)
            self.buildGroupBoxes()
            self.canvas.draw()
            self.rebuildPlot = False
            self.applySettings()
        else:
            newdata = response.get
            if newdata.shape[1] == 0:
                return
            if 'xAxisIsTime' in self.settings.keys() and self.settings['xAxisIsTime']:
                newdata[:,0] -= self.plotT0
                newdata[:,0] /= 60.0
            self.plotData = np.append(self.plotData, newdata, axis=0)
            # trim down to appropriate size
            if self.plotData.shape[0] > MAX_POINTS:
                self.plotData = self.plotData[(self.plotData.shape[0] - MAX_POINTS):, :]
            for i in range(1, newdata.shape[1]):
                line = self.lines[i-1]
                if self.tempUnitsCB.isChecked() and '[K]' in line.get_label():
                    line.set_data(self.plotData[:,0], (self.plotData[:,i]-273.15)*1.8 + 32)
                elif self.tempUnitsCB.isChecked() and '[C]' in line.get_label():
                    line.set_data(self.plotData[:,0], self.plotData[:,i]*1.8 + 32)
                else:
                    line.set_data(self.plotData[:,0], self.plotData[:,i])
            self.scalePlots()
            self.canvas.draw()

    def scalePlots(self):
        ''' scale the plots to show all the data. only use visible lines. account for absolute limits in settings. '''
        for plot, legend in zip(self.plots, self.plotLegends):
            # determine x max and min
            xmax, xmin = max(self.plotData[:,0]), min(self.plotData[:,0])
            if 'xlimits' in self.settings.keys():
                for leg, amin, amax in self.settings['xlimits']:
                    if legend in leg:
                        xmax = min(xmax, amax)
                        xmin = max(xmin, amin)
                        break
            try:
                m = float(str(self.minutesToDisplayEdit.text()))
                if m > 0:
                    xmin = max(xmin, xmax-m)
            except ValueError:
                pass
            # determine y max and min
            plotIndices = [x for x in self.plotIndices[legend] if self.lines[x-1].get_visible()]
            if not plotIndices:
                continue
            xinds = np.where(np.logical_and(self.plotData[:,0] >= xmin, self.plotData[:,0] <= xmax))[0]
            ymax, ymin = self.plotData[:,plotIndices][xinds].max(), self.plotData[:,plotIndices][xinds].min()
            #ymax, ymin = self.plotData[:,plotIndices].max(), self.plotData[:,plotIndices].min()
            yr = ymax-ymin
            ymax += yr*0.1
            ymin -= yr*0.1
            if 'ylimits' in self.settings.keys():
                for leg, amin, amax in self.settings['ylimits']:
                    if legend in leg:
                        ymax = min(ymax, amax)
                        ymin = max(ymin, amin)
                        break

            
            if self.rescaleXCB.isChecked():
                plot.set_xlim(xmax=xmax, xmin=xmin)
            if self.rescaleCB.isChecked():
                plot.set_ylim(ymax=ymax, ymin=ymin)
            
    def applySettings(self):
        ''' apply the plot settings in the settings dict.
        things like which plots are visible, axis limits, etc.'''
        if 'activeLines' in self.settings.keys():
            for cb in self.checkBoxes:
                cb.setChecked(False)
            for al in self.settings['activeLines']:
                for cb in self.checkBoxes:
                    if al.strip() == str(cb.text()).strip():
                        cb.setChecked(True)
        if 'activePlots' in self.settings.keys():
            for ap in self.settings['activePlots']:
                for gb in self.groupBoxes:
                    if ap in str(gb.title()):
                        gb.setChecked(True)
                    else:
                        gb.setChecked(False)
                    gb.leaveEvent(None)
            self.groupBoxCallback()
        self.hideUncheckedCB.setChecked(True)
        self.hideUncheckedCallback(True)
        #if 'ylimits' in self.settings.keys():
            #for name, lim in ylimits:
                
            
    def buildGroupBoxes(self):
        while True:
            it = self.groupBoxLayout.takeAt(1)
            if not it:
                break
            self.groupBoxLayout.removeItem(it)
        self.groupBoxes = []
        self.checkBoxes = []
        self.checkBoxesToLines = {}
        for legend in self.plotLegends:
            vl = Qt.QVBoxLayout()
            if len(self.plotLabels[legend]) == 1:
                gb = Qt.QGroupBox("%s (%s)" % (legend, self.plotLabels[legend][0]))
            else:
                gb = Qt.QGroupBox(legend)
                for label in self.plotLabels[legend]:
                    l = self.lines[self.plotIndices[legend][self.plotLabels[legend].index(label)] - 1]
                    cb = Qt.QCheckBox(label)
                    cb.setStyleSheet('QCheckBox {color: %s; font-weight: bold}' % l.get_color())
                    cb.setChecked(True)
                    cb.toggled.connect(self.checkBoxCallback)
                    vl.addWidget(cb)
                    self.checkBoxes.append(cb)
                    self.checkBoxesToLines[cb] = l
            gb.setCheckable(True)
            gb.setChecked(True)
            gb.setLayout(vl)
            gb.setSizePolicy(Qt.QSizePolicy.Fixed, Qt.QSizePolicy.Fixed)
            gb.clicked.connect(self.groupBoxCallback)
            self.groupBoxes.append(gb)
            self.groupBoxLayout.addWidget(gb, 0, QtCore.Qt.AlignTop)
            gb.leaveEvent(None)
        self.groupBoxLayout.addStretch()
        
            
    def checkBoxCallback(self):
        for cb in self.checkBoxes:
            self.checkBoxesToLines[cb].set_visible(cb.isChecked())
        self.scalePlots()
        self.canvas.draw()
        
    def groupBoxCallback(self):
        # count up number of active graphs
        numActive = 0
        for gb in self.groupBoxes:
            if gb.isChecked():
                numActive += 1
        # activate/deactivate
        i = 0
        for gb, plot in zip(self.groupBoxes, self.plots):
            if gb.isChecked():
                i+=1
                plot.set_visible(True)
                plot.change_geometry(numActive, 1, i)
                if i == numActive:
                    plt.setp(plot.get_xticklabels(), visible=True)
                    plot.set_xlabel(self.xlabel)
                else:
                    plt.setp(plot.get_xticklabels(), visible=False)
                    plot.set_xlabel('')
            else:
                plot.set_visible(False)
        self.canvas.draw()



class HidingGroupBox(Qt.QGroupBox):
    """
    When not moused over, hides any checkboxes inside itself that aren't checked.
    """
    def __init__(self, *args, **kwargs):
        Qt.QGroupBox.__init__(self, *args, **kwargs)
        self.setMouseTracking(True)

    def _items(self):
        return (self.layout().itemAt(i).widget() for i in range(self.layout().count()))

    def enterEvent(self, event=None):
        for w in self._items():
            w.setVisible(True)

    def leaveEvent(self, event=None):
        for w in self._items():
            if not w.isChecked():
                w.setVisible(False)

def make():
    demo = Qt.QWidget()

    widg = LabRADPlotWidget2(demo, path=["", "ADR", "quaid"], dataset=466)

    layout = Qt.QVBoxLayout(demo)
    layout.addWidget(widg)

    demo.resize(600, 400)
    demo.show()
    return demo

# make()


def main(args):
    app = Qt.QApplication(args)
    
    import qt4reactor
    qt4reactor.install()
    from twisted.internet import reactor
    import labrad, labrad.util, labrad.types
    
    demo = make()
    reactor.runReturn()
    sys.exit(app.exec_())

# main()


# Admire!
if __name__ == '__main__':
    main(sys.argv)
