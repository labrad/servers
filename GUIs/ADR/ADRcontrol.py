# ADR control panel code
# pyqt version

# By: Ted White, Peter O'Malley

import sys, labrad, time, math
from PyQt4 import QtCore,QtGui,uic,Qt
from twisted.internet.defer import inlineCallbacks, returnValue
from LabRADPlotWidget import LabRADPlotWidget

DEFAULT_ADR = 'quaid' # 'cause i'm lazy

def units_format(v, u=None):
    #prefix = dict(zip(range(-8, 9, 1), ['y', 'z', 'a', 'f', 'p', 'n', 'u' , 'm', '', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']))
    prefix = dict(zip(range(-8, 9, 1), ['y', 'z', 'a', 'f', 'p', 'n', u'\u03bc' , 'm', '', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']))
    numMoved = 0
    while v < 1:
        v *= 1000
        numMoved -= 1
    while v > 1000:
        v /= 1000
        numMoved += 1
    # how far to round?
    l = math.log(v, 10)
    if l < 1.0:
        v = '%.2f' % v
    elif l < 2.0:
        v = '%.1f' % v
    else:
        v = '%.0f' % v
    if u:
        u = ' ' + prefix[numMoved] + u
    elif numMoved:
        u = 'e' + str(numMoved*3)
    else:
        u = ''
    return v + u
    
class TestWindow (QtGui.QMainWindow):

    def __init__(self, cxn, default_adr):
        # some defaults
        self.adr_server_name = 'adr_server'
        self.adr_server_not_found_message = 'Server "%s" not found!' % self.adr_server_name
        self.peripheral_orphaned_message = 'Orphaned'
        self.peripheral_no_adr_message = ''
        self.default_adr = default_adr
        # initialize misc
        self.cxn = cxn
        self.adr_server = None

        # initialize the qt side of things
        QtGui.QMainWindow.__init__(self)
        ui_class, widget_class = uic.loadUiType("ADRcontrol.ui")
        self.ui = ui_class()
        self.ui.setupUi(self)
        self.setWindowTitle('ADR controls')
        self.setWindowIcon(QtGui.QIcon('ADR.png'))
        self.show()
        
        self.uiInit()

        # list of all the items that get disabled when in read-only mode
        self.protected = [self.ui.status_menu, self.ui.compressorStart_pushButton, self.ui.compressorStop_pushButton,
                            self.ui.closeHeatSwitch, self.ui.openHeatSwitch,
                            self.ui.quenchLimit_button, self.ui.cooldownLimit_button, self.ui.rampWaitTime_button,
                            self.ui.voltageStepDown_button, self.ui.voltageStepUp_button, self.ui.voltageLimit_button,
                            self.ui.maxCurrent_button, self.ui.switchPosition_button, self.ui.targetCurrent_button,
                            self.ui.autoControl, self.ui.schedulingActive,
                            self.ui.scheduledMagUpTime, self.ui.tempRecordDelay_button, self.ui.fieldWaitTime_button,
                            self.ui.autoRecord, self.ui.recordingTemp_button, self.ui.loggingStart_pushButton, self.ui.loggingStop_pushButton]
        
        # attempt to connect to labrad
        self.postConnectInitialize()
        # oh yeah
        self.ui.statusbar.showMessage("oh yeah")

    def uiInit(self):
        
        # the timer
        self.ui.timer = QtCore.QTimer(self)
        self.ui.timer.timeout.connect(self.update)
        self.ui.timer.start(500) # fire every 500 milliseconds
        
        # these are just holder lists so we can iterate easily
        self.tempLabels = [self.ui.temperatures1, self.ui.temperatures2, self.ui.temperatures3, self.ui.temperatures4, 
                        self.ui.temperatures5, self.ui.temperatures6, self.ui.temperatures7, self.ui.temperatures8]
        self.voltLabels = [self.ui.voltages1, self.ui.voltages2, self.ui.voltages3, self.ui.voltages4, 
                        self.ui.voltages5, self.ui.voltages6, self.ui.voltages7, self.ui.voltages8]
        
    
    def postConnectInitialize(self):
        # this function initializes the ui elements that need a labrad connection
        # add the plotter to the appropriate tab
        self.ui.plot = LabRADPlotWidget(self.ui.temperaturePlot, cxn=self.cxn, horizontal=False, yAxisIsDate=True)
        self.ui.temperaturePlot_layout.addWidget(self.ui.plot)
        # populate the ADR selection combo box
        self.ui.ADR_device_combo.clear()
        if self.cxn.servers.has_key(self.adr_server_name):
            self.adr_server = self.cxn.servers[self.adr_server_name]
            # get devices
            devNames = map(lambda x: x[1], self.adr_server.list_devices())
            self.ui.ADR_device_combo.addItems(devNames)
            if self.default_adr and self.ui.ADR_device_combo.findText(self.default_adr) != -1:
                self.ui.ADR_device_combo.setCurrentIndex(self.ui.ADR_device_combo.findText(self.default_adr))
            # get statuses
            statuses = self.adr_server.list_statuses()
            self.ui.status_menu.clear()
            self.ui.status_menu.addItems(statuses)
            # set alignment
            self.ui.status_menu.setStyleSheet("QComboBox {text-align:center}")
            #m = self.ui.status_menu.model();
            #m.setData(m.index(0,0), Qt.QVariant(Qt.Qt.AlignCenter), Qt.Qt.TextAlignmentRole)
            #for i in range(self.ui.status_menu.count()):
            #	self.ui.status_menu.setItemData(i, Qt.Qt.AlignCenter, Qt.Qt.TextAlignmentRole)
        else:
            self.ui.ADR_device_combo.addItem(self.adr_server_not_found_message)
    
    #######################
    # THE UPDATE FUNCTION #
    #######################
    @QtCore.pyqtSlot()
    @inlineCallbacks
    def update(self):
        """ this gets repeatedly called to update the data displayed """
        if self.cxn is None:
            return
        if self.adr_server is None:
            # set the peripheral text boxes to nothing
            self.ui.PNALineEdit.setText(self.peripheral_no_adr_message)
            self.ui.compressorLineEdit.setText(self.peripheral_no_adr_message)
            self.ui.heatSwitchLineEdit.setText(self.peripheral_no_adr_message)
            self.ui.lakeshoreLineEdit.setText(self.peripheral_no_adr_message)
            self.ui.magnetLineEdit.setText(self.peripheral_no_adr_message)
        try:
            # read temperatures
            temps = self.adr_server.temperatures()
            volts = self.adr_server.voltages()
            for i in range(len(self.tempLabels)):
                self.tempLabels[i].setText("%3.3f" % (temps[i].value))
                self.voltLabels[i].setText("%3.3f" % (volts[i].value))
            
            liVolt = yield self.adr_server.get_state('lockinVoltage')
            if liVolt is None:
                self.ui.voltageLockin.setText('--')
            else:
                self.ui.voltageLockin.setText(units_format(liVolt['V'], 'V'))
            
            
            #read magnet (power supply) status	
            (psC, psV) = self.adr_server.magnet_status()
            self.ui.psVoltage_label.setText("%.3f" % psV)
            self.ui.psCurrent_label.setText("%.4f" % psC)
            
            # read compressor status
            running = self.adr_server.compressor_status()
            if running:
                self.ui.compressorStart_pushButton.setEnabled(False)
                if not self.ui.readOnly_checkBox.isChecked():
                    self.ui.compressorStop_pushButton.setEnabled(True)
                self.ui.compressorStatus_label.setText("<font color='green'>Compressor Started</font>")
            else:
                if not self.ui.readOnly_checkBox.isChecked():
                    self.ui.compressorStart_pushButton.setEnabled(True)
                self.ui.compressorStop_pushButton.setEnabled(False)
                self.ui.compressorStatus_label.setText("<font color='dark green'>Compressor Stopped</font>")

            # set the status drop down
            status = yield self.adr_server.status()
            self.ui.status_menu.setCurrentIndex(self.ui.status_menu.findText(str(status)))

            # update the ruox / cold stage resistance and temperature
            temp, res = self.adr_server.ruox_status()
            self.ui.coldStageTemp.setText("%.4f" % float(temp.value))
            self.ui.coldStageRes.setText("%.4f" % (float(res.value) / 10**3)) # in kOhm
                
            # set peripheral text boxes. there's probably a way to do this all quick and python like, but whatever.
            if self.ui.tabWidget.currentWidget() == self.ui.LabRAD:
                boxes = [('PNA', self.ui.PNALineEdit), ('compressor', self.ui.compressorLineEdit), ('heatswitch', self.ui.heatSwitchLineEdit),
                        ('lakeshore', self.ui.lakeshoreLineEdit), ('magnet', self.ui.magnetLineEdit), ('temperature_lockin', self.ui.temperatureLockInLineEdit),]
                connected_list = self.adr_server.list_connected_peripherals()
                orphan_list = self.adr_server.list_orphans()
                connecteds = {}
                orphans = {}
                for name, dev in connected_list:
                    connecteds[name] = dev
                for name, dev in orphan_list:
                    orphans[name] = dev
                for name, box in boxes:
                    if name in connecteds.keys():
                        box.setText(connecteds[name])
                    elif name in orphans.keys():
                        box.setText(self.peripheral_orphaned_message)
                    else:
                        box.setText('Peripheral "%s" not found' % name)
                        
            elif self.ui.tabWidget.currentWidget() == self.ui.fridge:
                # read ADR state variables and set appropriate displays
                # list of text boxes to update
                textBoxes = ['quenchLimit', 'cooldownLimit', 'rampWaitTime', 'voltageStepUp', 'voltageStepDown', 'voltageLimit',
                            'targetCurrent', 'maxCurrent', 'switchPosition', 'lockinCurrent', 'remainingTimeAtField', 'magDownTimer',
                            'PIDsetTemp', 'PIDcd', 'PIDcp', 'PIDci', 'PIDintLimit', 'PIDstepTimeout']
                # check boxes to update
                checkBoxes = ['waitToMagDown', 'autoControl']
                for state in self.adr_server.list_state_variables():
                    if state in self.ui.__dict__.keys():
                        # funny business for a couple (i.e. boolean instead of whatever)
                        if state in checkBoxes:
                            self.ui.__dict__[state].setChecked(bool(self.adr_server.get_state(state)))
                        elif state in textBoxes:
                            self.ui.__dict__[state].setText(str(self.adr_server.get_state(state)))
                        else:
                            pass
                
                
            elif self.ui.tabWidget.currentWidget() == self.ui.schedule:
                # scheduling active?
                sa = bool(self.adr_server.get_state('schedulingActive'))
                self.ui.schedulingActive.setChecked(sa)
                if sa:
                    self.ui.schedulingActive.setText("Scheduling (currently active)")
                else:
                    self.ui.schedulingActive.setText("Scheduling (currently inactive)")
                    
                # update the time widgets
                self.setDateTimeLabels(self.ui.currentTimeDate, self.ui.currentTimeTime, time.time())
                self.setDateTimeLabels(self.ui.scheduledMagUpTimeDate, self.ui.scheduledMagUpTimeTime, self.adr_server.get_state('scheduledMagUpTime'))
                self.setDateTimeLabels(self.ui.magUpCompletedDate, self.ui.magUpCompletedTime, self.adr_server.get_state('magUpCompletedTime'))
                self.setDateTimeLabels(self.ui.magDownCompletedDate, self.ui.magDownCompletedTime, self.adr_server.get_state('magDownCompletedTime'))
                self.setDateTimeLabels(self.ui.scheduledMagDownTimeDate, self.ui.scheduledMagDownTimeTime, self.adr_server.get_state('scheduledMagDownTime'))

                self.ui.fieldWaitTime.setText(str(self.adr_server.get_state('fieldWaitTime')))
                
                # the timeSince labels are used to display the time since mag up completed or time since mag down completed
                if status == 'waiting at field' or status == 'ready to mag down':
                    self.ui.timeSince_label.setText('Time Magged Up (min):')
                    self.ui.timeSince_label2.setText(str(round((time.time() - self.adr_server.get_state('magUpCompletedTime')) / 60.0, 2)))
                elif status == 'ready' and self.adr_server.get_state('magDownCompletedTime') > 1:
                    self.ui.timeSince_label.setText('Time Magged Down (min):')
                    self.ui.timeSince_label2.setText(str(round((time.time() - self.adr_server.get_state('magDownCompletedTime')) / 60.0, 2)))
                else:
                    self.ui.timeSince_label.setText('[time since mag up/down]')
                    self.ui.timeSince_label2.setText('n/a')
                
                
                
                # update the temp recording/logging widgets
                recording = self.adr_server.is_recording()
                if recording:
                    self.ui.loggingStart_pushButton.setEnabled(False)
                    if not self.ui.readOnly_checkBox.isChecked():
                        self.ui.loggingStop_pushButton.setEnabled(True)
                    self.ui.loggingStatus_label.setText("<font color='green'>Logging</font>")
                else:
                    if not self.ui.readOnly_checkBox.isChecked():
                        self.ui.loggingStart_pushButton.setEnabled(True)
                    self.ui.loggingStop_pushButton.setEnabled(False)
                    self.ui.loggingStatus_label.setText("<font color='dark green'>Not Logging</font>")
                
                self.ui.tempRecordDelay.setText(str(self.adr_server.get_state('tempRecordDelay')))
                self.ui.autoRecord.setChecked(bool(self.adr_server.get_state('autoRecord')))
                self.ui.recordingTemp.setText(str(self.adr_server.get_state('recordingTemp')))

                
            elif self.ui.tabWidget.currentWidget() == self.ui.log:
                text = ''
                for date, entry in self.adr_server.get_log():
                    text = '%s -- %s\n' % (date, entry) + text
                if text != str(self.ui.log_textEdit.toPlainText()):
                    self.ui.log_textEdit.setText(text)
                    
            elif self.ui.tabWidget.currentWidget() == self.ui.temperaturePlot:
                # find the latest dataset
                path = ["", "ADR", str(self.ui.ADR_device_combo.currentText())]
                dataset = self.adr_server.get_state('tempDatasetName')
                # get the current one
                currentDS = self.ui.plot.getDataset()
                # do we need to change datasets?
                if (not currentDS[1] or (path != currentDS[0] and dataset not in currentDS[1])) and dataset:
                    print "setting current dataset to %s %s" % (str(path), str(dataset))
                    self.ui.plot.setDataset(path, dataset)
        
        except labrad.errors.Error, e:
            print e
    # end of the update function #
    
    ############################################
    ### HERE BEGIN THE UI CALLBACK FUNCTIONS ###
    ############################################
    
    # when a new ADR is selected from the combo box
    @QtCore.pyqtSlot(str)
    def on_ADR_device_combo_currentIndexChanged(self, string):
        if string == self.adr_server_not_found_message:
            pass
        else:
            try:
                self.adr_server.select_device(str(string))
            except Exception, e:
                print e
    
    # when we go to and from read-only mode
    @QtCore.pyqtSlot(int)
    def on_readOnly_checkBox_stateChanged(self, newState):
        if newState == QtCore.Qt.Unchecked:
            # unlock the controls
            map(lambda x: x.setEnabled(True), self.protected)
        elif newState == QtCore.Qt.Checked:
            # lock the controls
            map(lambda x: x.setEnabled(False), self.protected)
    
    # start and stop the compressor
    @QtCore.pyqtSlot()
    def on_compressorStart_pushButton_clicked(self):
        self.adr_server.set_compressor(True)
    @QtCore.pyqtSlot()
    def on_compressorStop_pushButton_clicked(self):
        self.adr_server.set_compressor(False)
    
    # start and stop logging
    @QtCore.pyqtSlot()
    def on_loggingStart_pushButton_clicked(self):
        self.adr_server.start_recording()
    @QtCore.pyqtSlot()
    def on_loggingStop_pushButton_clicked(self):
        self.adr_server.stop_recording()
    def on_loggingReset_pushButton_clicked(self):
        self.adr_server.set_state('tempDatasetName', False)

        
    # open and close the heat switch
    @QtCore.pyqtSlot()
    def on_openHeatSwitch_clicked(self):
        check = QtGui.QMessageBox.question(self, 'For real?', "Are you sure you want to OPEN the heat switch?", QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
        if check == QtGui.QMessageBox.Yes:
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window, QtCore.Qt.green)
            self.ui.openHeatSwitch_label.setPalette(pal)
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window, QtCore.Qt.darkGreen)
            self.ui.closeHeatSwitch_label.setPalette(pal)
            self.adr_server.set_heat_switch(True)
    @QtCore.pyqtSlot()
    def on_closeHeatSwitch_clicked(self):
        check = QtGui.QMessageBox.question(self, 'For real?', "Are you sure you want to CLOSE the heat switch?", QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
        if check == QtGui.QMessageBox.Yes:
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window, QtCore.Qt.darkGreen)
            self.ui.openHeatSwitch_label.setPalette(pal)
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window, QtCore.Qt.green)
            self.ui.closeHeatSwitch_label.setPalette(pal)
            self.adr_server.set_heat_switch(False)

    # when the user changes the status
    # note that we use activated not currentIndexChanged so that we don't catch the programatically created ones
    @QtCore.pyqtSlot(str)
    def on_status_menu_activated(self, string):
        print string
        self.adr_server.change_status(str(string))
    
    # when user clicks button to refresh peripherals
    @QtCore.pyqtSlot()
    def on_refreshPeripherals_button_clicked(self):
        self.adr_server.refresh_peripherals()
        
    @QtCore.pyqtSlot()
    def on_refreshGPIB_button_clicked(self):
        self.adr_server.refresh_gpib()
    
    # schedule and temperature recording tab #
    @QtCore.pyqtSlot()
    def on_autoRecord_clicked(self):
        self.adr_server.set_state('autoRecord', self.ui.autoRecord.isChecked())
    @QtCore.pyqtSlot()
    def on_schedulingActive_clicked(self):
        self.adr_server.set_state('schedulingActive', self.ui.schedulingActive.isChecked())
    
    # handle all of the "set" buttons
    @QtCore.pyqtSlot()
    def on_quenchLimit_button_clicked(self):
        self.setState("quenchLimit")
    @QtCore.pyqtSlot()
    def on_cooldownLimit_button_clicked(self):
        self.setState("cooldownLimit")
    @QtCore.pyqtSlot()
    def on_rampWaitTime_button_clicked(self):
        self.setState("rampWaitTime")
    @QtCore.pyqtSlot()
    def on_voltageStepUp_button_clicked(self):
        self.setState("voltageStepUp")
    @QtCore.pyqtSlot()
    def on_voltageStepDown_button_clicked(self):
        self.setState("voltageStepDown")
    @QtCore.pyqtSlot()
    def on_voltageLimit_button_clicked(self):
        self.setState("voltageLimit")
    @QtCore.pyqtSlot()
    def on_targetCurrent_button_clicked(self):
        self.setState("targetCurrent")
    @QtCore.pyqtSlot()
    def on_maxCurrent_button_clicked(self):
        self.setState("maxCurrent")
    @QtCore.pyqtSlot()
    def on_fieldWaitTime_button_clicked(self):
        self.setState("fieldWaitTime")
    @QtCore.pyqtSlot()
    def on_switchPosition_button_clicked(self):
        self.setState("switchPosition")
    @QtCore.pyqtSlot()
    def on_lockinCurrent_button_clicked(self):
        self.setState("lockinCurrent")
    @QtCore.pyqtSlot()
    def on_autoControl_clicked(self):
        self.adr_server.set_state('autoControl', bool(self.ui.autoControl.isChecked()))
    @QtCore.pyqtSlot()
    def on_scheduledMagUpTime_clicked(self):
        self.setDateTimeState('scheduledMagUpTime', self.ui.scheduledMagUpTimeDate.text(), self.ui.scheduledMagUpTimeTime.text())
    @QtCore.pyqtSlot()
    def on_recordingTemp_button_clicked(self):
        self.setState("recordingTemp")
    @QtCore.pyqtSlot()
    def on_tempRecordDelay_button_clicked(self):
        self.setState("tempRecordDelay")
    @QtCore.pyqtSlot()
    def on_PIDsetTemp_button_clicked(self):
        self.setState("PIDsetTemp")
    @QtCore.pyqtSlot()
    def on_PIDcp_button_clicked(self):
        self.setState("PIDcp")
    @QtCore.pyqtSlot()
    def on_PIDcd_button_clicked(self):
        self.setState("PIDcd")
    @QtCore.pyqtSlot()
    def on_PIDstepTimout_button_clicked(self):
        self.setState("PIDstepTimeout")
    @QtCore.pyqtSlot()
    def on_PIDci_button_clicked(self):
        self.setState("PIDci")
    @QtCore.pyqtSlot()
    def on_PIDintLimit_button_clicked(self):
        self.setState("PIDintLimit")

        
    def setState(self, var):
        val, ok = QtGui.QInputDialog.getText(self, var, "New value for %s:" % var)
        # this is a hack, need to fix
        try:
            val = int(val)
        except ValueError:
            val = float(val)
        if ok:
            self.adr_server.set_state(var, val)
            
    def setDateTimeLabels(self, dateLabel, timeLabel, t):
        if t > 1:
            lt = time.localtime(t)
            dateLabel.setText("%s/%s" % (lt.tm_mon, lt.tm_mday))
            timeLabel.setText("%s:%02d" % (lt.tm_hour, lt.tm_min))
        else:
            dateLabel.setText("-")
            timeLabel.setText("-")
        
    def setDateTimeState(self, var, d, t):
        val, ok = QtGui.QInputDialog.getText(self, var, "New value for %s:" % var, QtGui.QLineEdit.Normal, "%s %s" % (d, t))
        if ok:
            d, t = str(val).split()
            mon, day = d.split('/')
            hr, min = t.split(":")
            year = time.localtime().tm_year
            newTime = time.mktime(time.strptime("%s/%s/%s %s:%s" % (mon, day, year, hr, min), "%m/%d/%Y %H:%M"))
            self.adr_server.set_state(var, newTime)


# end of the class, here is the boilerplate that runs the thing
# take the name of the default ADR from the command line, if applicable
if __name__ == "__main__":
    if len(sys.argv) > 1:
            default_adr = sys.argv[1]
    else:
            default_adr = DEFAULT_ADR
    app = QtGui.QApplication(sys.argv)
    with labrad.connect() as cxn:
        window = TestWindow(cxn, default_adr)
        sys.exit(app.exec_())

