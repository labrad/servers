# ADR control panel code
# pyqt version

# By: Ted White, Peter O'Malley
import sys
import time
import math

from PyQt4 import QtCore, QtGui, uic
from twisted.internet.defer import inlineCallbacks

from LabRADPlotWidget2 import LabRADPlotWidget2


DEFAULT_ADR = 'quaid'  # 'cause i'm lazy


def units_format(v, u=None):
    # prefix = dict(zip(range(-8, 9, 1),
    # ['y', 'z', 'a', 'f', 'p', 'n', 'u' , 'm', '', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']))
    prefix = dict(zip(range(-8, 9, 1),
                      ['y', 'z', 'a', 'f', 'p', 'n', u'\u03bc', 'm', '', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']))
    num_moved = 0
    while v < 1:
        v *= 1000
        num_moved -= 1
    while v > 1000:
        v /= 1000
        num_moved += 1
    # how far to round?
    l = math.log(v, 10)
    if l < 1.0:
        v = '%.2f' % v
    elif l < 2.0:
        v = '%.1f' % v
    else:
        v = '%.0f' % v
    if u:
        u = ' ' + prefix[num_moved] + u
    elif num_moved:
        u = 'e' + str(num_moved * 3)
    else:
        u = ''
    return v + u


# noinspection PyPep8Naming
class TestWindow(QtGui.QMainWindow):
    def __init__(self, _default_adr):
        # some defaults
        self.adr_server_name = 'adr_server'
        self.adr_server_not_found_message = 'Server "%s" not found!' % self.adr_server_name
        self.peripheral_orphaned_message = 'Orphaned'
        self.peripheral_no_adr_message = ''
        self.default_adr = _default_adr
        # initialize misc
        self.cxn = None
        self.adr_server = None
        cxn_def = labrad.wrappers.connectAsync(name=labrad.util.getNodeName() + ' ADR GUI')
        cxn_def.addCallback(self.set_cxn)
        self.waitingOnLabRAD = True

        # initialize the qt side of things
        QtGui.QMainWindow.__init__(self)
        ui_class, widget_class = uic.loadUiType("ADRcontrol.ui")
        self.ui = ui_class()
        self.ui.setupUi(self)
        self.setWindowTitle('ADR controls')
        self.setWindowIcon(QtGui.QIcon('ADR.png'))
        self.show()

        self.ui_init()

        # list of all the items that get disabled when in read-only mode
        self.protected = [self.ui.refreshPeripherals_button, self.ui.refreshGPIB_button, self.ui.refreshDefaults_button,
                          self.ui.status_menu, self.ui.compressorStart_pushButton, self.ui.compressorStop_pushButton,
                          self.ui.closeHeatSwitch, self.ui.openHeatSwitch,
                          self.ui.quenchLimit_button, self.ui.cooldownLimit_button, self.ui.rampWaitTime_button,
                          self.ui.voltageStepDown_button, self.ui.voltageStepUp_button, self.ui.voltageLimit_button,
                          self.ui.maxCurrent_button, self.ui.targetCurrent_button,
                          self.ui.ruoxTempCutoff_button, self.ui.lockinOhmsPerVolt_button,
                          self.ui.autoControl, self.ui.delayHeatSwitchClose, self.ui.schedulingActive,
                          self.ui.scheduledMagUpTime, self.ui.tempRecordDelay_button, self.ui.fieldWaitTime_button,
                          self.ui.autoRecord, self.ui.recordingTemp_button, self.ui.loggingStart_pushButton,
                          self.ui.loggingStop_pushButton, self.ui.loggingReset_pushButton]

        # oh yeah
        self.ui.statusbar.showMessage("oh yeah")

    @inlineCallbacks
    def set_cxn(self, cxn):
        self.cxn = cxn
        self.adr_server = self.cxn.adr_server
        yield self.post_connect_initialize()
        self.waitingOnLabRAD = False

    # noinspection PyAttributeOutsideInit
    def ui_init(self):
        # these are just holder lists so we can iterate easily
        self.tempLabels = [self.ui.temperatures1, self.ui.temperatures2, self.ui.temperatures3, self.ui.temperatures4,
                           self.ui.temperatures5, self.ui.temperatures6, self.ui.temperatures7, self.ui.temperatures8]
        self.voltLabels = [self.ui.voltages1, self.ui.voltages2, self.ui.voltages3, self.ui.voltages4,
                           self.ui.voltages5, self.ui.voltages6, self.ui.voltages7, self.ui.voltages8]

        # list of text boxes to update
        self.textBoxes = ['quenchLimit', 'cooldownLimit', 'rampWaitTime', 'voltageStepUp', 'voltageStepDown',
                          'voltageLimit',
                          'targetCurrent', 'maxCurrent', 'lockinOhmsPerVolt', 'ruoxTempCutoff',
                          'PIDsetTemp', 'PIDcd', 'PIDcp', 'PIDci', 'PIDintLimit', 'PIDstepTimeout']
        # check boxes to update
        self.checkBoxes = ['autoControl', 'delayHeatSwitchClose']
        # state variables for scheduling
        self.schedulingStates = ['schedulingActive', 'scheduledMagUpTime', 'scheduledMagDownTime', 'magUpCompletedTime',
                                 'magDownCompletedTime', 'fieldWaitTime']
        # temp recording state variables
        self.tempRecordingStates = ['tempRecordDelay', 'autoRecord', 'recordingTemp']
        self.datasetNameState = ['tempDatasetName']

        # the timer
        self.ui.timer = QtCore.QTimer(self)
        # noinspection PyUnresolvedReferences
        self.ui.timer.timeout.connect(self.update)
        self.ui.timer.start(200)  # fire every 500 milliseconds

    @inlineCallbacks
    def post_connect_initialize(self):
        # this function initializes the ui elements that need a labrad connection
        # add the plotter to the appropriate tab
        settings = {'activePlots': ['temperature'],
                    'activeLines': ['ch1: 50K', 'ch2: 4K', 'ch3: mag', 'ruox', 'magnet'],
                    'ylimits': [['temperature', 0, 325], ['current', 0, 60]], 'xAxisIsTime': True}
        self.ui.plot = LabRADPlotWidget2(self.ui.temperaturePlot, cxn=self.cxn, timer=self.ui.timer, settings=settings)
        self.ui.temperaturePlot_layout.addWidget(self.ui.plot)
        # populate the ADR selection combo box
        self.ui.ADR_device_combo.clear()
        if self.adr_server_name in self.cxn.servers:
            self.adr_server = self.cxn.servers[self.adr_server_name]
            # get devices
            dev_names = map(lambda x: x[1], (yield self.adr_server.list_devices()))
            self.ui.ADR_device_combo.addItems(dev_names)
            if self.default_adr and self.ui.ADR_device_combo.findText(self.default_adr) != -1:
                self.ui.ADR_device_combo.setCurrentIndex(self.ui.ADR_device_combo.findText(self.default_adr))
            # get statuses
            statuses = yield self.adr_server.list_statuses()
            self.ui.status_menu.clear()
            self.ui.status_menu.addItems(statuses)
            # set alignment
            self.ui.status_menu.setStyleSheet("QComboBox {text-align:center}")
        else:
            self.ui.ADR_device_combo.addItem(self.adr_server_not_found_message)

    # #######################
    # THE UPDATE FUNCTIONS #
    # #######################
    @QtCore.pyqtSlot()
    def update(self):
        """ this gets repeatedly called to update the data displayed """
        if self.cxn is None:
            return
        if self.adr_server is None:
            # set the peripheral text boxes to nothing
            self.ui.compressorLineEdit.setText(self.peripheral_no_adr_message)
            self.ui.heatSwitchLineEdit.setText(self.peripheral_no_adr_message)
            self.ui.lakeshoreLineEdit.setText(self.peripheral_no_adr_message)
            self.ui.magnetLineEdit.setText(self.peripheral_no_adr_message)
            return
        if self.waitingOnLabRAD:
            return
        self.waitingOnLabRAD = True
        p = self.adr_server.packet()
        p.temperatures()
        p.voltages()
        p.magnet_status()
        p.compressor_status()
        p.status()
        p.ruox_status()
        p.list_connected_peripherals()
        p.list_orphans()
        for t in self.textBoxes + self.checkBoxes + self.schedulingStates + self.tempRecordingStates \
                + self.datasetNameState:
            p.get_state(t, key=t)
        p.is_recording()
        p.get_log()
        d = p.send()
        d.addCallback(self.updateCallback)
        d.addErrback(self.update_errback)

    def updateCallback(self, response):
        self.waitingOnLabRAD = False
        # read temperatures
        for i in range(len(self.tempLabels)):
            self.tempLabels[i].setText("%3.3f" % (response.temperatures[i]['K']))
            self.voltLabels[i].setText("%3.3f" % (response.voltages[i]['V']))

        # read magnet (power supply) status
        self.ui.psCurrent_label.setText("%.4f" % response.magnet_status[0]['A'])
        self.ui.psVoltage_label.setText("%.3f" % response.magnet_status[1]['V'])

        # read compressor status
        if response.compressor_status:
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
        self.ui.status_menu.setCurrentIndex(self.ui.status_menu.findText(str(response.status)))

        # update the ruox / cold stage resistance and temperature
        self.ui.coldStageTemp.setText("%.4f" % float((response.ruox_status[0])['K']))
        self.ui.coldStageRes.setText("%.4f" % float((response.ruox_status[1])['kOhm']))  # in kOhm

        boxes = [('compressor', self.ui.compressorLineEdit), ('heatswitch', self.ui.heatSwitchLineEdit),
                 ('lakeshore', self.ui.lakeshoreLineEdit), ('magnet', self.ui.magnetLineEdit)]
        connecteds = {}
        orphans = {}
        for name, dev in response.list_connected_peripherals:
            connecteds[name] = dev
        for name, dev in response.list_orphans:
            orphans[name] = dev
        for name, box in boxes:
            if name in connecteds.keys():
                box.setText(connecteds[name])
            elif name in orphans.keys():
                box.setText(self.peripheral_orphaned_message)
            else:
                box.setText('Peripheral "%s" not found' % name)

        # read ADR state variables and set appropriate displays
        for state in self.textBoxes:
            self.ui.__dict__[state].setText(str(response[state]))
        for state in self.checkBoxes:
            self.ui.__dict__[state].setChecked(bool(response[state]))

        # scheduling active?
        self.ui.schedulingActive.setChecked(response.schedulingActive)
        if response.schedulingActive:
            self.ui.schedulingActive.setText("Scheduling (currently active)")
        else:
            self.ui.schedulingActive.setText("Scheduling (currently inactive)")

        # update the time widgets
        self.setDateTimeLabels(self.ui.currentTimeDate, self.ui.currentTimeTime, time.time())
        self.setDateTimeLabels(self.ui.scheduledMagUpTimeDate, self.ui.scheduledMagUpTimeTime,
                               response.scheduledMagUpTime)
        self.setDateTimeLabels(self.ui.magUpCompletedDate, self.ui.magUpCompletedTime, response.magUpCompletedTime)
        self.setDateTimeLabels(self.ui.magDownCompletedDate, self.ui.magDownCompletedTime,
                               response.magDownCompletedTime)
        self.setDateTimeLabels(self.ui.scheduledMagDownTimeDate, self.ui.scheduledMagDownTimeTime,
                               response.scheduledMagDownTime)

        self.ui.fieldWaitTime.setText(str(response.fieldWaitTime))

        # the timeSince labels are used to display the time since mag up completed or time since mag down completed
        if response.status == 'waiting at field' or response.status == 'ready to mag down':
            self.ui.timeSince_label.setText('Time Magged Up (min):')
            self.ui.timeSince_label2.setText(str(round(((time.time() - response.magUpCompletedTime['s']) / 60.0), 2)))
        elif response.status == 'ready' and response.magDownCompletedTime > 1:
            self.ui.timeSince_label.setText('Time Magged Down (min):')
            self.ui.timeSince_label2.setText(str(round(((time.time() - response.magUpCompletedTime['s']) / 60.0), 2)))
        else:
            self.ui.timeSince_label.setText('[time since mag up/down]')
            self.ui.timeSince_label2.setText('n/a')

        # update the temp recording/logging widgets
        if response.is_recording:
            self.ui.loggingStart_pushButton.setEnabled(False)
            if not self.ui.readOnly_checkBox.isChecked():
                self.ui.loggingStop_pushButton.setEnabled(True)
            self.ui.loggingStatus_label.setText("<font color='green'>Logging</font>")
        else:
            if not self.ui.readOnly_checkBox.isChecked():
                self.ui.loggingStart_pushButton.setEnabled(True)
            self.ui.loggingStop_pushButton.setEnabled(False)
            self.ui.loggingStatus_label.setText("<font color='dark green'>Not Logging</font>")

        self.ui.tempRecordDelay.setText(str(response.tempRecordDelay))
        self.ui.autoRecord.setChecked(bool(response.autoRecord))
        self.ui.recordingTemp.setText(str(response.recordingTemp))

        text = ''
        for date, entry in response.get_log:
            text = '%s -- %s\n' % (date, entry) + text
        if text != str(self.ui.log_textEdit.toPlainText()):
            self.ui.log_textEdit.setText(text)

        # find the latest dataset
        path = ["", "ADR", str(self.ui.ADR_device_combo.currentText())]
        dataset = response.tempDatasetName
        cur_dataset = self.ui.plot.getDataset()
        if dataset and (not cur_dataset or dataset not in cur_dataset):
            print path, dataset
            self.ui.plot.setDataset(path=path, dataset=dataset)
            # get the current one
            #currentDS = self.ui.plot.getDataset()
            # do we need to change datasets?
            #if (not currentDS[1] or (path != currentDS[0] and dataset not in currentDS[1])) and dataset:
            #    print "setting current dataset to %s %s" % (str(path), str(dataset))
            #    self.ui.plot.setDataset(path, dataset)

    def update_errback(self, failure):
        self.waitingOnLabRAD = False
        failure.trap(labrad.types.Error)
        if "DeviceNotSelectedError" in failure.getTraceback():
            self.adr_server.select_device()
            # print "selecting device"
        else:
            print failure

    # end of the update functions #

    # ###########################################
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

    @QtCore.pyqtSlot()
    def on_openHeatSwitch_clicked(self):
        # noinspection PyCallByClass
        check = QtGui.QMessageBox.question(self, 'For real?', "Are you sure you want to OPEN the heat switch?",
                                           QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
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
        # noinspection PyCallByClass
        check = QtGui.QMessageBox.question(self, 'For real?', "Are you sure you want to CLOSE the heat switch?",
                                           QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
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

    @QtCore.pyqtSlot()
    def on_refreshDefaults_button_clicked(self):
        self.adr_server.revert_to_defaults()

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
    def on_lockinOhmsPerVolt_button_clicked(self):
        self.setState("lockinOhmsPerVolt")

    @QtCore.pyqtSlot()
    def on_ruoxTempCutoff_button_clicked(self):
        self.setState("ruoxTempCutoff")

    @QtCore.pyqtSlot()
    def on_autoControl_clicked(self):
        self.adr_server.set_state('autoControl', bool(self.ui.autoControl.isChecked()))

    @QtCore.pyqtSlot()
    def on_delayHeatSwitchClose_clicked(self):
        self.adr_server.set_state('delayHeatSwitchClose', bool(self.ui.delayHeatSwitchClose.isChecked()))

    @QtCore.pyqtSlot()
    def on_scheduledMagUpTime_clicked(self):
        self.setDateTimeState('scheduledMagUpTime', self.ui.scheduledMagUpTimeDate.text(),
                              self.ui.scheduledMagUpTimeTime.text())

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

    # noinspection PyCallByClass
    @inlineCallbacks
    def setState(self, var):
        old_value = yield self.adr_server.get_state(var)
        if hasattr(old_value, 'unit'):
            oldUnit = old_value.unit
        else:
            oldUnit = units.Unit('')
        val, ok = QtGui.QInputDialog.getText(self, var, "New value for %s [%s]:" % (var, oldUnit))
        # pull out units, if any
        val, _, unit = str(val).strip().partition(' ')
        try:
            val = int(val)
        except ValueError:
            val = float(val)
        if unit:
            unit = units.Unit(unit)
            if not unit.isCompatible(oldUnit):
                QtGui.QMessageBox.warning(self, "Unit Mismatch", "%s and %s are not compatible." % (oldUnit, unit))
                ok = False
        else:
            unit = oldUnit
        # this is a hack, need to fix
        if ok:
            yield self.adr_server.set_state(var, val * unit)

    def setDateTimeLabels(self, dateLabel, timeLabel, t):
        if hasattr(t, 'unit') and t.unit != '':
            if t['s'] > 1:
                lt = time.localtime(t['s'])
                dateLabel.setText("%s/%s" % (lt.tm_mon, lt.tm_mday))
                timeLabel.setText("%s:%02d" % (lt.tm_hour, lt.tm_min))
            else:
                dateLabel.setText("-")
                timeLabel.setText("-")
        else:
            if t > 1:
                lt = time.localtime(t)
                dateLabel.setText("%s/%s" % (lt.tm_mon, lt.tm_mday))
                timeLabel.setText("%s:%02d" % (lt.tm_hour, lt.tm_min))
            else:
                dateLabel.setText("-")
                timeLabel.setText("-")

    def setDateTimeState(self, var, d, t):
        val, ok = QtGui.QInputDialog.getText(self, var, "New value for %s:" % var, QtGui.QLineEdit.Normal,
                                             "%s %s" % (d, t))
        if ok:
            d, t = str(val).split()
            mon, day = d.split('/')
            hr, minute = t.split(":")
            year = time.localtime().tm_year
            newTime = time.mktime(time.strptime("%s/%s/%s %s:%s" % (mon, day, year, hr, minute), "%m/%d/%Y %H:%M"))
            self.adr_server.set_state(var, newTime)


# end of the class, here is the boilerplate that runs the thing
# take the name of the default ADR from the command line, if applicable
if __name__ == "__main__":
    if len(sys.argv) > 1:
        default_adr = sys.argv[1]
    else:
        default_adr = DEFAULT_ADR
    app = QtGui.QApplication(sys.argv)
    import qt4reactor

    qt4reactor.install()
    from twisted.internet import reactor
    import labrad
    import labrad.util
    import labrad.types
    import labrad.units as units

    reactor.runReturn()
    window = TestWindow(default_adr)
    ret_val = app.exec_()
    reactor.threadpool.stop()
    sys.exit(ret_val)
