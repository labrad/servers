import sys
import os
import time
import labrad
from PyQt4 import Qt,QtCore,QtGui,uic
from numpy import sort

import os

import numpy as np
import matplotlib.pyplot as plt
import sys

from labrad.units import V, torr, A, degC, min, h, d, y, K

from pyle import registry, datavault
from pyle.workflow import switchSession


cxn = labrad.connect()


reg = cxn.registry
dv = cxn.data_vault

class MainWindow (QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        ui_class, widget_class = uic.loadUiType("MBEStatus.ui")
        self.ui = ui_class()
        self.ui.setupUi(self)
        self.show()
        
    @QtCore.pyqtSlot()
    def getTime(self):
        year = str(time.localtime()[0])[2:]
        if len(str(time.localtime()[1])) == 1:
            month = '0' + str(time.localtime()[1])
        else:
            month = str(time.localtime()[1])
        if len(str(time.localtime()[2])) == 1:
            day = '0' + str(time.localtime()[2])
        else:
            day = str(time.localtime()[2])
        curTime = str(time.localtime()[3])+':'+str(time.localtime()[4])+':'+str(time.localtime()[5])
        dateTime = year + month + day + '(' + curTime + ')'
        
        return dateTime
    #type = string, float, pressure
    def checkAddParameter(self,name,parameter,type):
        if type == 'QComboBox':
                dv.add_parameter(name,str(parameter.currentText()))
        elif parameter.toPlainText() != '':
            if type == 'str':
                dv.add_parameter(name,str(parameter.toPlainText()))
            if type == 'float':
                dv.add_parameter(name,float(parameter.toPlainText()))
            if type == 'pressure':
                if parameter == self.ui.igPressure:
                    dv.add_parameter(name,float(parameter.toPlainText())*10**(float(self.ui.igExponent.toPlainText())))
                if parameter == self.ui.bfmPressure:
                    dv.add_parameter(name,float(parameter.toPlainText())*10**(float(self.ui.bfmExponent.toPlainText())))
                if parameter == self.ui.bufferPressure:
                    dv.add_parameter(name,float(parameter.toPlainText())*10**(float(self.ui.bufferExponent.toPlainText())))
                if parameter == self.ui.llPressure:
                    dv.add_parameter(name,float(parameter.toPlainText())*10**(float(self.ui.llExponent.toPlainText())))
                    
                
        else:
            print name, ' is empty.'
    
    def writeData(self):
        dv.cd(['','MBE'])
        dateTime = self.getTime()
        date = dateTime[:6]
        time = dateTime[7:-1]
        if str(self.ui.waferName.toPlainText()) == '':
            print 'Wafer has no name!!!'
        else:
            name = str(self.ui.waferName.toPlainText())
            dv.cd(name,True)
            dv.cd(date,True)
            # dv.cd('Test')
            dv.new(str(self.ui.processType.currentText()) + ' ' + time, ['time'],['parameters'])
            dv.add_parameter('date',date)
            dv.add_parameter('time',time)
            dv.add_parameter('style',1.1)
            self.checkAddParameter('state',self.ui.processType,'QComboBox')
            self.checkAddParameter('Name',self.ui.waferName,'string')
            self.checkAddParameter('Comments',self.ui.notes,'string')
            self.checkAddParameter('Pressure IG (torr)',self.ui.igPressure,'pressure')
            self.checkAddParameter('Pressure BFM (torr)',self.ui.bfmPressure,'pressure')
            self.checkAddParameter('Pressure Buffer (torr)',self.ui.bufferPressure,'pressure')
            self.checkAddParameter('Pressure Load Lock (torr)',self.ui.llPressure,'pressure')
            self.checkAddParameter('Temp Cryo (K)',self.ui.cryoTemp,'float')
            self.checkAddParameter('Temp Substrate (C)',self.ui.subTemp,'float')
            dv.add_parameter('Thermocouple Type in Eurotherm','S')
            # dv.add_parameter('Thermocouple Type in Eurotherm','C')
            self.checkAddParameter('Temp Load Lock (C)',self.ui.llTemp,'float')
            self.checkAddParameter('Temp Water (C)',self.ui.waterTemp,'float')
            self.checkAddParameter('Power Substrate Eurotherm (W)',self.ui.euroPower,'float')
            self.checkAddParameter('Voltage Substrate Eurotherm (V)',self.ui.euroVolt,'float')
            self.checkAddParameter('Current Substrate Eurotherm (A)',self.ui.euroCurrent,'float')
            self.checkAddParameter('Spin Rate LL Turbo (kRPM)',self.ui.llSpinRate,'float')
            self.checkAddParameter('Power LL Turbo (W)',self.ui.llPower,'float')
            self.checkAddParameter('Temp LL Turbo (C)',self.ui.llTurboTemp,'float')
            self.checkAddParameter('Spin Rate Main Turbo (kRPM)',self.ui.mainSpinRate,'float')
            self.checkAddParameter('Power Main Turbo (W)',self.ui.mainPower,'float')
            self.checkAddParameter('Temp 1 Main Turbo (C)',self.ui.mainTemp1,'float')
            self.checkAddParameter('Temp 2 Main Turbo (C)',self.ui.mainTemp2,'float')
    
    def pressurePlot(self):
        
        fig = plt.figure()
        fig.suptitle('pressure vs time', fontsize = 30)
        ax = fig.add_subplot(111)
        ax.set_xlabel('date year\month\day')
        ax.set_ylabel('Pressure (torr)')
        ax.set_yscale('log')
        
        return ax
    
    def tempPlot(self,unit='C'):
        
        fig = plt.figure()
        fig.suptitle('Temperature vs time', fontsize = 30)
        ax = fig.add_subplot(111)
        ax.set_xlabel('date year\month\day')
        ax.set_ylabel('Temperature ' + '(' + unit + ')')
        
        return ax
        
    def spinPlot(self):
        
        fig = plt.figure()
        fig.suptitle('Spin Rate vs time', fontsize = 30)
        ax = fig.add_subplot(111)
        ax.set_xlabel('date year\month\day')
        ax.set_ylabel('Spin Rate (kRPM)')
        
        return ax
        
    def powPlot(self):
        
        fig = plt.figure()
        fig.suptitle('Power vs time', fontsize = 30)
        ax = fig.add_subplot(111)
        ax.set_xlabel('date year\month\day')
        ax.set_ylabel('Power (W)')
        
        return ax
    
    def voltPlot(self):
        
        fig = plt.figure()
        fig.suptitle('Voltage vs time', fontsize = 30)
        ax = fig.add_subplot(111)
        ax.set_xlabel('date year\month\day')
        ax.set_ylabel('Voltage (V)')
        
        return ax
        
    def currentPlot(self):
        
        fig = plt.figure()
        fig.suptitle('Current vs time', fontsize = 30)
        ax = fig.add_subplot(111)
        ax.set_xlabel('date year\month\day')
        ax.set_ylabel('Current (A)')
        
        return ax
        
    
    @QtCore.pyqtSlot()
    def plotHistory(self):
        
        plotState = str(self.ui.plotProcess.currentText())
        plotType = str(self.ui.plotType.currentText())
        
        
        
        if plotType[:4] == 'Spin':
            ax = self.spinPlot()
            
        elif plotType[:4] == 'Temp':
            if plotType[-3:] == '(K)':
                ax = self.tempPlot(unit='K')
            else:
                ax = self.tempPlot()
                
            
        elif plotType[:5] == 'Power':
            ax = self.powPlot()
        
        elif plotType[:5] == 'Power':
            ax = self.powPlot()
        
        elif plotType[:5] == 'Power':
            ax = self.powPlot()
        
        else:
            ax = self.pressurePlot()
            
        dv.cd(['','MBE'])
        
        dateTimeList = []
        plotParamList = []
        
        plotWafer = str(self.ui.plotWaferName.toPlainText())
        
        if plotWafer == 'all':
            for wafer in dv.dir()[0]:
                if wafer != 'Test' and wafer != '140616' and wafer != '140617':
                    dv.cd(wafer)
                    for date in dv.dir()[0]:
                        dv.cd(date)
                        dvw = datavault.DataVaultWrapper(dv.cd(),cxn)
                        if plotState == 'all':
                            for dataDex in range(1,len(dvw.keys())+1):
                                for paramDex in range(len(dvw[dataDex].parameters)):
                                    if plotType in dvw[dataDex].parameters:
                                        plotParamList.append(dvw[dataDex].parameters[plotType].value)
                                        dateTimeList.append(float(dvw[dataDex].parameters['date'])+.1*dataDex)
                        else:
                            for dataDex in range(1,len(dvw.keys())+1):
                                if 'state' in dvw[dataDex].parameters:
                                    if dvw[dataDex].parameters['state'] == plotState:
                                        if plotType in dvw[dataDex].parameters:
                                            plotParamList.append(dvw[dataDex].parameters[plotType].value)
                                            dateTimeList.append(float(dvw[dataDex].parameters['date'])+.1*dataDex)
                        dv.cd(1)
                    dv.cd(1)
        else:
            dv.cd(plotWafer)
            for date in dv.dir()[0]:
                        dv.cd(date)
                        dvw = datavault.DataVaultWrapper(dv.cd(),cxn)
                        if plotState == 'all':
                            for dataDex in range(1,len(dvw.keys())+1):
                                for paramDex in range(len(dvw[dataDex].parameters)):
                                    if plotType in dvw[dataDex].parameters:
                                        plotParamList.append(dvw[dataDex].parameters[plotType].value)
                                        dateTimeList.append(float(dvw[dataDex].parameters['date'])+.1*dataDex)
                        else:
                            for dataDex in range(1,len(dvw.keys())+1):
                                if 'state' in dvw[dataDex].parameters:
                                    if dvw[dataDex].parameters['state'] == plotState:
                                        if plotType in dvw[dataDex].parameters:
                                            plotParamList.append(dvw[dataDex].parameters[plotType].value)
                                            dateTimeList.append(float(dvw[dataDex].parameters['date'])+.1*dataDex)
            
            dv.cd(1)
        
        print 'time list = ', dateTimeList
        print 'param list = ', plotParamList
        ax.plot(dateTimeList,plotParamList,'bo',label = plotType,ms =7,ls='-')
        ax.legend(loc='best',ncol=2,fancybox=True,shadow=True)
        plt.show()
        
        return 
        
    def on_writeDataButton_released(self):  
        self.writeData()
        # for plainText in self.ui.
            # self.ui.plainText.clear()
    
    def on_plotHistoryButton_released(self):  
        self.plotHistory()
        
app = QtGui.QApplication(sys.argv)
window = MainWindow()
sys.exit(app.exec_())