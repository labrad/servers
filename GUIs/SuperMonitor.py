#!/usr/bin/python
'''
SuperMonitor.py
New and improved DR monitor.
'''

import sys
from twisted.internet.defer import inlineCallbacks, Deferred

import PyQt4.Qt as Qt
import PyQt4.QtGui as QtGui
import PyQt4.QtCore as QtCore

from LabRADPlotWidget3 import LabRADPlotWidget3

DEFAULT = 'Vince'
BASE_PATH = ['', 'DR']
NODE_LOOKUP = {'node_vince': 'Vince', 'node_dr': 'Jules', 'node_ivan': 'Ivan'}
LOGGER_SERVER = 'DR Logger'

class AppForm(Qt.QMainWindow):
    def __init__(self, path=None):
        Qt.QMainWindow.__init__(self)
        self.init_qt()
        self.path = path
        try:
            import labrad
            cxnDef = labrad.connectAsync(name=labrad.util.getNodeName() + ' SuperMonitor')
        except AttributeError:
            import labrad.async
            cxnDef = labrad.async.connectAsync(name=labrad.util.getNodeName() + ' SuperMonitor')
        cxnDef.addCallback(self.set_cxn)
        cxnDef.addErrback(self.err_cxn)
    
    def init_qt(self):
        self.setWindowTitle('SuperMonitor')
        self.resize(1920*0.5,1280*0.5)
    
    @inlineCallbacks
    def set_cxn(self, cxn):
        self.cxn = cxn
        # look for the node to determine what fridge we're connected to.
        if self.path is None:
            for node, path in NODE_LOOKUP.items():
                if node in cxn.servers:
                    self.path = BASE_PATH + [path]
                    print 'Found %s, using directory %s' % (node,path)
                    yield self.check_dr_logger(cxn.servers[node])
                    break
            else:
                self.path = BASE_PATH + [DEFAULT]
                print 'Using default directory %s' % DEFAULT
        dv = self.cxn.data_vault
        yield dv.cd(self.path)
        dirs = yield dv.dir()
        self.dataset = dirs[1][-1]
        self.plotWidget = LabRADPlotWidget3(self, self.cxn, self.path, self.dataset, drLoggerName='DR Logger')
        self.setCentralWidget(self.plotWidget)
        # a bit hackish, but whatever
        self.plotWidget.historyLE.setText('60m')
        self.plotWidget.xAxisUnitsLE.setText("min")
        self.plotWidget.zeroXAxisCB.setChecked(True)
        self.plotWidget.maxPointsLE.setText('1000')

    @inlineCallbacks
    def err_cxn(self, failure):
        print "Connection failure!"
        message = "Could not connect to LabRAD:\n" + ':\n'.join(failure.getErrorMessage().split(':'))
        label = Qt.QLabel(message)
        label.setAlignment(QtCore.Qt.AlignHCenter)
        label.setStyleSheet("* {font-weight: bold; font-size: 15pt;}")
        self.setCentralWidget(label)
        # wait and do it again
        d = Deferred()
        reactor.callLater(1, d.callback, 1)
        yield d
        try:
            import labrad
            cxnDef = labrad.connectAsync(name=labrad.util.getNodeName() + ' SuperMonitor')
        except AttributeError:
            import labrad.async
            cxnDef = labrad.async.connectAsync(name=labrad.util.getNodeName() + ' SuperMonitor')
        cxnDef.addCallback(self.set_cxn)
        cxnDef.addErrback(self.err_cxn)


    @inlineCallbacks
    def check_dr_logger(self, node):
        running = yield node.running_servers()
        if LOGGER_SERVER not in [x[0] for x in running] + list(self.cxn.servers):
            print "%s not running, attempting to start... " % LOGGER_SERVER,
            try:
                yield node.start(LOGGER_SERVER)
                print "started."
            except labrad.types.Error:
                print "failed."
                QtGui.QMessageBox.warning(self, "No Logging Server",
                    "%s is not running on the node and could not be started.\n" % LOGGER_SERVER + \
                    "If it isn't running, your data won't be updated!")
        else:
            print "%s running" % LOGGER_SERVER
        
    def closeEvent(self, event):
        try:
            self.cxn.disconnect()
        except BaseException as ex:
            print ex

if __name__ == '__main__':        
    # look for DR name in args
    if len(sys.argv) > 1:
        DEFAULT = sys.argv[1]
    app = Qt.QApplication(sys.argv)
    import qt4reactor
    qt4reactor.install()
    from twisted.internet import reactor
    import labrad, labrad.util, labrad.types
    reactor.runReturn()
    form = AppForm()
    form.show()
    v = app.exec_()
    reactor.threadpool.stop()
    sys.exit(v)    
