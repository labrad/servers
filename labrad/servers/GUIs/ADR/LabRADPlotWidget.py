import os, sys, labrad, time

import PyQt4.Qt as Qt
import PyQt4.QtCore as QtCore
import PyQt4.Qwt5 as Qwt
from PyQt4.QtGui import QColor, QPen, QPalette
from PyQt4.Qwt5.anynumpy import *
from twisted.internet.defer import inlineCallbacks, returnValue
import numpy as np
import matplotlib.cbook as mpc


class TimeScaleDraw(Qwt.QwtScaleDraw):
    """ Helper class to draw label the time axis correctly. """
    def label(self, value):
        str = time.strftime("%m-%d %H:%M", time.localtime(int(value)))
        return Qwt.QwtText(str)

class LabRADPlot(Qwt.QwtPlot):
    """ Qt plot widget inheriting Qwt.QwtPlot for plotting a labrad dataset. """
    # the curve colors we'll cycle through.
    curveColors = [QColor('black'), QColor('darkblue'), QColor('crimson'), QColor('darkgoldenrod'),
                    QColor('violet'), QColor('deeppink'), QColor('darkgrey'), QColor('olivedrab')]

    def __init__(self, parent, cxn=None, path=[], dataset=None):
        Qwt.QwtPlot.__init__(self, parent)

        # dictionary of curves
        self.curves = {}
        self.currentLabel = None
        
        # LabRAD stuff
        self.path = path
        self.dataset = dataset
        self.cxn = cxn
        if not self.cxn:
            self.cxn = labrad.connect()
            
        # misc stuff
        self.drawingRect = False	# whether or not we're currently drawing a rect
        self.previousScales = []
        self.xmin = 0
        self.xmax = 0
        self.ymin = 0
        self.ymax = 0
    
    def setConnection(self, cxn):
        self.cxn = cxn
    
    def setPath(self, path):
        self.path = path
        
    def setDataset(self, dataset, path=None):
        #print "plot %s %s" % (str(path), dataset)
        if path is not None:
            self.setPath(path)
        self.dataset = dataset
        
    def getDataset(self):
        return (self.dataset, self.path)

    def setScaleDraw(self, isTime):
        if isTime:
            self.setAxisScaleDraw(Qwt.QwtPlot.xBottom, TimeScaleDraw())
            self.setAxisLabelRotation(Qwt.QwtPlot.xBottom, -50)
            self.setAxisLabelAlignment(Qwt.QwtPlot.xBottom, Qt.Qt.AlignLeft | Qt.Qt.AlignBottom)
        else:
            self.setAxisScaleDraw(Qwt.QwtPlot.xBottom, Qwt.QwtScaleDraw())
            self.setAxisLabelRotation(Qwt.QwtPlot.xBottom, 0);
            self.setAxisLabelAlignment(Qwt.QwtPlot.xBottom, Qt.Qt.AlignHCenter | Qt.Qt.AlignBottom)
        self.replot()

    
    # load the data from a dataset
    def loadData(self):
        if not self.dataset:
            return
        dv = self.cxn.data_vault
        dv.cd(self.path)
        # if we have a string for the dataset, do some logic to find the correct one
        if type(self.dataset) == str:
            dirs, sets = dv.dir()
            found = False
            for set in sets:
                if self.dataset in set:
                    self.dataset = set
                    found = True
                    break
            if not found:
                print "unable to find dataset %s in %s" % (self.dataset, str(self.path))
                return
        
        # load the data
        dv.open(self.dataset)
        self.independents, self.dependents = dv.variables()
        self.curves = {}
        self.data =  dv.get(-1, True).asarray # get us some data!
        # the xdata is the same for all curves--the first element
        self.xdata = self.data[:,0]
        
        self.setAxisTitle(Qwt.QwtPlot.xBottom, self.independents[0][0])
        self.legendColors = {}
        i = 1
        lastColor = 0
        for label, legend, units in self.dependents:
            # make a curve
            curve = Qwt.QwtPlotCurve(legend)
            # rotate through colors, keep the same color if we have the same name
            color = self.getLegendColor(legend)
            if not color:
                color = self.curveColors[lastColor % len(self.curveColors)]
                self.legendColors[legend] = color
                lastColor += 1
            curve.setPen(QPen(color, 2.0))
            
            # set the data of the curve -- the x data was already calculated, the y data are in the i'th element
            curve.setData(self.xdata, self.data[:,i])
            if label not in self.curves.keys():
                self.curves[label] = {}
            # put this curve in the dict by label and legend
            self.curves[label][legend] = curve
            curve.attach(self)
            curve.setVisible(False)
            i += 1
        self.replot()
    
    def getLegendColor(self, legend):
        if self.legendColors and (legend in self.legendColors.keys()):
            return self.legendColors[legend]
        else:
            return None
    
    def refreshData(self):
        if not self.dataset:
            return
        dv = self.cxn.data_vault
        newdata = dv.get().asarray
        # if there's no new data, dv.get will return [[]]
        if not len(newdata):
            return
        self.data = np.append(self.data, newdata, axis=0)
        self.xdata = self.data[:,0]
        newYs = []
        i = 1
        for label, legend, units in self.dependents:
            curve = self.curves[label][legend]
            curve.setData(self.xdata, self.data[:,i])
            if curve.isVisible():
                newYs.extend(newdata[:,i])
            i += 1

        self.ymin = min(min(newYs), self.ymin)
        self.ymax = max(max(newYs), self.ymax)
        self.rescale(xmin=self.xmin, ymin=self.ymin, ymax=self.ymax, pushScale = False)
        self.replot()
        
    def selectLabel(self, label):
        if label in self.curves.keys():
            self.currentLabel = label
            self.setAxisTitle(Qwt.QwtPlot.yLeft, label)
            self.rescale()
            self.replot()
            self.previousScales = []
        else:
            print "No label %s" % label
            
    def showCurve(self, legend, show):
        if legend in self.curves[self.currentLabel].keys():
            self.curves[self.currentLabel][legend].setVisible(show)
            self.rescale()
            self.replot()
            #print "showing curve %s in label %s" % (legend, self.currentLabel)
        else:
            print "No legend %s in label %s" % (legend, self.currentLabel)
            
    def printCurves(self):
        for label in self.curves.keys():
            for legend in self.curves[label].keys():
                if self.curves[label][legend].isVisible():
                    print "visible: %s %s" % (label, legend)
                else:
                    print "not visible: %s %s" % (label, legend)
    
    def rescale(self, xmin='auto', xmax='auto', ymin='auto', ymax='auto', pushScale = True):
        ''' rescale the plot, auto-calcing appropriate xmin, xmax, ymin, ymax if necessary.
        also, push the previous scale onto the current stack of scale histories.
        a call to self.popScale will then go back to the previous scale. nifty, huh?'''
        if self.currentLabel:
            if pushScale and self.xmin != 0 and self.ymin != 0 and self.xmax != 0 and self.ymax != 0:
                self.previousScales.append([self.xmin, self.xmax, self.ymin, self.ymax])
            # autocalc xmin, ymin, xmax, ymax if necessary
            if xmin == 'auto':
                xmin = min(self.xdata)
            if xmax == 'auto':
                xmax = max(self.xdata)
            ys = []
            if (ymin == 'auto') or (ymax == 'auto'):
                for leg in self.curves[self.currentLabel]:
                    if self.curves[self.currentLabel][leg].isVisible():
                        ys.extend(self.curves[self.currentLabel][leg].data().yData())
                if not ys:
                    return
            if (ymax == 'auto'):
                ymax = max(ys)
            if (ymin == 'auto'):
                ymin = min(ys)
            self.setAxisScale(Qwt.QwtPlot.xBottom, xmin, xmax)
            self.setAxisScale(Qwt.QwtPlot.yLeft, ymin, ymax)
            self.xmin = xmin
            self.xmax = xmax
            self.ymin = ymin
            self.ymax = ymax
    
    def popScale(self):
        if len(self.previousScales):
            newScale = self.previousScales[-1]
            self.previousScales = self.previousScales[:-1]
            self.rescale(*newScale, pushScale = False)
        else:
            self.rescale(pushScale = False)
        self.replot()
        #print self.previousScales
    
    def getLabels(self):
        return self.curves.keys()
    
    def getLegends(self, label):
        if label in self.curves.keys():
            return self.curves[label].keys()
        else:
            return None
    

    # the mouse events handle drawing rects on the graph to zoom
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            # figure out where on the plot we clicked, and save it
            self.xDown = e.pos().x()
            self.yDown = e.pos().y()
            self.drawingRect = True
        if e.button() == QtCore.Qt.RightButton:
            # if we were drawing a rect, cancel it
            if self.drawingRect:
                self.drawingRect = False
            else:
                # if we weren't, pop the top of the previousScales stack and rescale one
                self.popScale()
            self.replot()
        
    def mouseMoveEvent(self, e):
        self.xNow = e.pos().x()
        self.yNow = e.pos().y()
        if self.drawingRect:
            self.replot()
            
    def mouseReleaseEvent(self, e):
        if self.drawingRect and e.button() == QtCore.Qt.LeftButton:
            pos = e.pos()
            canvasRect = self.plotLayout().canvasRect()
            # now figure out the data value of the point we let up on
            x = pos.x() - canvasRect.x()
            y = canvasRect.height() - pos.y()
            x = max(x, 0);
            x = min(x, canvasRect.width());
            y = max(y, 0);
            y = min(y, canvasRect.height());
            xData2 = x * ((self.xmax - self.xmin) / canvasRect.width()) + self.xmin;
            yData2 = y * ((self.ymax - self.ymin) / canvasRect.height()) + self.ymin;
            # and that of the point we clicked before
            x = self.xDown - canvasRect.x()
            y = canvasRect.height() - self.yDown
            x = max(x, 0);
            x = min(x, canvasRect.width());
            y = max(y, 0);
            y = min(y, canvasRect.height());
            xData1 = x * ((self.xmax - self.xmin) / canvasRect.width()) + self.xmin;
            yData1 = y * ((self.ymax - self.ymin) / canvasRect.height()) + self.ymin;
            # finally, rescale our plot
            self.drawingRect = False
            newScale = [min(xData1, xData2), max(xData1, xData2), min(yData1, yData2), max(yData1, yData2)]
            self.rescale(*newScale)
            self.replot()
            
            
    def drawItems(self, painter, rect, map, pfilter):
        Qwt.QwtPlot.drawItems(self, painter, rect, map, pfilter)
        if self.drawingRect:
            offset = self.plotLayout().canvasRect().x()
            painter.drawRect(min(self.xDown, self.xNow) - offset, min(self.yDown, self.yNow), abs(self.xDown - self.xNow), abs(self.yDown - self.yNow))
        
# A Qt Widget wrapper with some added functionality for selecting parts of a dataset		
class LabRADPlotWidget(Qt.QWidget):

    def __init__(self, parent, cxn=None, path=[], dataset=None, horizontal=True, yAxisIsDate = False):
        """
        A Qt widget that plots a labrad dataset.
        You can provide it a labrad connection if you like (otherwise it does labrad.connect()),
        and a path and dataset name (or number). You can set those later, too.
        The last argument (horizontal) determines the layout of the widget.
        If true, then the control buttons are to the right of the plot. If false, below.
        """
        
        Qt.QWidget.__init__(self, parent)
        
        # create our component objects
        self.plot = LabRADPlot(self, cxn=cxn, path=path, dataset=dataset)
        self.labelButtonGroup = Qt.QGroupBox(self)
        self.legendCheckGroup = Qt.QGroupBox(self)
        self.labelLayout = Qt.QVBoxLayout(self.labelButtonGroup)
        self.legendLayout = Qt.QVBoxLayout(self.legendCheckGroup)
        self.labelButtons = []
        self.legendChecks = []
        self.watchCheckBox = Qt.QCheckBox("Watch data for changes", self)
        self.watchCheckBox.clicked.connect(self.watchCheckBox_clicked)
        self.xScaleCheckBox = Qt.QCheckBox("Draw x-axis as date", self)
        self.xScaleCheckBox.clicked.connect(self.xScaleCheckBox_clicked)
        print "ADSFASDER"
        self.plot.loadData()
        if horizontal:
            self.layout = Qt.QHBoxLayout(self)
            layout2 = Qt.QVBoxLayout()			# layout 2 has the plot controls
        else:
            self.layout = Qt.QVBoxLayout(self)
            layout2 = Qt.QHBoxLayout()
        
        self.titleLabel = Qt.QLabel("<b>Dataset: %s</b>" % self.formatDatasetName())
        self.titleLabel.setAlignment(QtCore.Qt.AlignHCenter)
        self.layout.addWidget(self.titleLabel)	
        self.layout.addWidget(self.plot)		# plot goes on the left
        anotherLayout = Qt.QVBoxLayout()
        anotherLayout.addWidget(self.watchCheckBox)
        anotherLayout.addWidget(self.xScaleCheckBox)
        layout2.addItem(anotherLayout)
        layout2.addWidget(self.labelButtonGroup)
        layout2.addWidget(self.legendCheckGroup)
        spacer = Qt.QSpacerItem(0,0, Qt.QSizePolicy.Minimum, Qt.QSizePolicy.Minimum)
        layout2.addItem(spacer)
        self.layout.addItem(layout2)			# layout2 goes on the right
        
        self.loadButtons()
        
        # timer
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.time = 1000 # 1000 ms
        if yAxisIsDate:
            self.xScaleCheckBox.setChecked(True)
            self.plot.setScaleDraw(True)
        
    def formatDatasetName(self):
        dataset, path = self.plot.getDataset()
        p = ''
        for dir in path:
            if dir:
                p += '/%s' % dir
        return "%s/%s" % (p, dataset)
        
    def watchCheckBox_clicked(self):
        if self.watchCheckBox.isChecked():
            self.timer.start(self.time)
        else:
            self.timer.stop()
            
    def xScaleCheckBox_clicked(self):
        self.plot.setScaleDraw(self.xScaleCheckBox.isChecked())
    
    def loadButtons(self):
        """
        Load the appropriate buttons for this dataset.
        One radio button for every label (e.g. resistance, temperature, etc)
        When the user selects a button, we make a checkbox for every legend (e.g. ruox 1, ruox 2, etc)
        """
        if len(self.legendChecks):
            for c in self.legendChecks:
                if c.isChecked():
                    c.click()
                self.legendLayout.removeWidget(c)
                c.setParent(None)
        if len(self.labelButtons):
            for b in self.labelButtons:
                self.labelLayout.removeWidget(b)
                b.setParent(None)
        self.labelButtons = []
        self.legendChecks = []
        for l in self.plot.getLabels():
            b = Qt.QRadioButton(l)
            b.clicked.connect(self.loadChecks)
            self.labelButtons.append(b)
            self.labelLayout.addWidget(b)
            
    def loadChecks(self):
        """
        Make a checkbox for each legend in this label.
        """
        # find the selected button
        for b in self.labelButtons:
            if b.isChecked():
                label = str(b.text())
                
        # out with the old
        for c in self.legendChecks:
            if c.isChecked():
                c.click()
            self.legendLayout.removeWidget(c)
            c.setParent(None)
        self.legendChecks = []
        
        self.plot.selectLabel(label)
        
        # in with the new
        for l in self.plot.getLegends(label):
            c = Qt.QCheckBox(l)
            color = self.plot.getLegendColor(l)
            if color:
                p = c.palette()
                p.setColor(QPalette.WindowText, color)
                c.setPalette(p)
            c.clicked.connect(self.make_callback(l))
            self.legendChecks.append(c)
            self.legendLayout.addWidget(c)
            c.click()

    def make_callback(self, legend):
        """ a function that returns a function. oh, yeah... """
        return lambda checked: self.plot.showCurve(legend, checked)
        
    def setDataset(self, newpath, dataset):
        #print "widget %s %s" % (str(newpath), dataset)
        self.plot.setDataset(dataset, path=newpath)
        self.plot.loadData()
        self.loadButtons()
        self.titleLabel.setText("<b>Dataset: %s</b>" % self.formatDatasetName())
        
    def refresh(self):
        """ Adds any new data to the plot. """
        self.plot.refreshData()
        
    def getDataset(self):
        """ Returns the current dataset and the current path. """
        return (self.plot.path, self.plot.dataset)
        


def make():
    demo = Qt.QWidget()

    widg = LabRADPlotWidget(demo, cxn=labrad.connect(), path=["", "ADR", "hauser"], dataset=53, horizontal=False, yAxisIsDate=True)

    layout = Qt.QVBoxLayout(demo)
    layout.addWidget(widg)

    demo.resize(600, 400)
    demo.show()
    return demo

# make()


def main(args):
    app = Qt.QApplication(args)
    demo = make()
    sys.exit(app.exec_())

# main()


# Admire!
if __name__ == '__main__':
    main(sys.argv)