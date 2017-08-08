import sys
import labrad
from PyQt4 import Qt,QtCore,QtGui,uic
from numpy import sort
import time

###########################################################################################
# Version History
# 7/28/13 - Fixed ordering of microwave connections in the key
# 7/26/13 - Added new backup functionality to folder and now loads key on initialization.
# 7/20/13 - Created by Jimmy Chen
###########################################################################################

wiringDir = 'Wiring'

with labrad.connect() as cxn:
    reg = cxn.registry
    
    class MainWindow (QtGui.QMainWindow):
        def __init__(self):
            QtGui.QMainWindow.__init__(self)
            ui_class, widget_class = uic.loadUiType("wireedit.ui")
            self.ui = ui_class()
            self.ui.setupUi(self)
            self.loadKey('wiring')
            self.show()
            
        def loadKey(self,keyname): #Read from the registry and format the data for the GUI
            reg.cd(['','Servers','Qubit Server',wiringDir])
            self.originalKey = reg.get(keyname)
            deviceList = self.originalKey[0]
            dcConnect = list(self.originalKey[1])
            uwaveConnect = list(self.originalKey[2])
            
            uwaveDeviceList = []
            dcDeviceList = []
            uwaveSourceList = []
            for device in deviceList:
                if device[0] == 'MicrowaveSource':
                    uwaveSourceList.append(device)
                elif device[0] == 'Preamp' or device[0] == 'FastBias':
                    dcDeviceList.append(device)
                else:
                    uwaveDeviceList.append(device)

            for [listtype,tabletype] in [[uwaveDeviceList,self.ui.uwaveDeviceTable],
                                         [dcDeviceList,self.ui.dcDeviceTable],
                                         [uwaveSourceList,self.ui.uwaveSourceTable],
                                         [dcConnect,self.ui.dcCxnTable],
                                         [uwaveConnect,self.ui.uwaveCxnTable]]:

                tabletype.setRowCount(len(listtype))
                
                for i,device in enumerate(listtype):
                    for j,prop in enumerate(device):
                        if listtype == dcDeviceList and j==2:
                            widgetprop = QtGui.QTableWidgetItem(str([float(gain) for gain in prop[0][1]])) 
                            tabletype.setItem(i,j,widgetprop)

                        elif listtype == dcConnect:
                            widgetprop = QtGui.QTableWidgetItem(str(prop[0]))  
                            widgetprop.property = device
                            tabletype.setItem(i,0+2*j,widgetprop)                        
                            widgetprop = QtGui.QTableWidgetItem(str(prop[1]))  
                            widgetprop.property = device
                            tabletype.setItem(i,1+2*j,widgetprop)                        
     
                        else:
                            widgetprop = QtGui.QTableWidgetItem(str(prop))  
                            tabletype.setItem(i,j,widgetprop)
                                                
                        widgetprop.property = device #Give every item the full registry entry as a 'property', 
                                                     #a monkey-patched attr of the widget class. Makes it easy to write to the key at the end.
                tabletype.resizeColumnsToContents()
                
            uwaveBoardTypes = reg.get('uwaveBoardTypes')
            dcBoardTypes = reg.get('dcBoardTypes')
            Fridges = reg.get('Fridges')
            Numbers = [str(i) for i in range(1,25)]
            

            self.ui.uwaveBoardSelector.insertItems(1,uwaveBoardTypes)
            self.ui.dcBoardSelector.insertItems(1,dcBoardTypes)
            self.ui.sourceFridgeSelector.insertItems(1,Fridges)
            self.ui.dcFridgeSelector.insertItems(1,Fridges)
            self.ui.uwaveFridgeSelector.insertItems(1,Fridges)
            self.ui.sourceNumberSelector.insertItems(1,Numbers)
            self.ui.dcNumberSelector.insertItems(1,Numbers)
            self.ui.uwaveNumberSelector.insertItems(1,Numbers)
            
            self.ui.ioSelect.insertItems(1,['in','out0','out1'])
            self.ui.channelSelect.insertItems(1,['A','B','C','D'])
        
        @QtCore.pyqtSlot()
        def on_loadKeyButton_released(self):
            self.loadKey('wiring')
            
        @QtCore.pyqtSlot()
        def on_loadBackupButton_released(self):
            self.loadKey('wiringBackup')
 
        @QtCore.pyqtSlot()
        def on_readBackButton_released(self):  
        #Print out to command line, for debugging, does not exist in UI anymore
            numrows = self.ui.deviceTable.rowCount()
            for i in range(numrows):
                print self.ui.deviceTable.item(i,1).property
         
        @QtCore.pyqtSlot()
        def on_uwaveAddButton_released(self):  
            row = self.ui.uwaveDeviceTable.rowCount()
            self.ui.uwaveDeviceTable.insertRow(row)
            
            type = str(self.ui.uwaveBoardSelector.currentText()) 
            fridge = str(self.ui.uwaveFridgeSelector.currentText())
            number = str(self.ui.uwaveNumberSelector.currentText())

            if type=='AdcBoard':
                name = fridge+' ADC'+' '+number
            else:
                name = fridge+' DAC'+' '+number
            
            typeQ=QtGui.QTableWidgetItem(type)
            nameQ=QtGui.QTableWidgetItem(name)

            nameQ.property=(type,name)
            self.ui.uwaveDeviceTable.setItem(row,0,typeQ)
            self.ui.uwaveDeviceTable.setItem(row,1,nameQ)

        @QtCore.pyqtSlot()
        def on_dcAddButton_released(self):  
            
            type = str(self.ui.dcBoardSelector.currentText()) 
            fridge = str(self.ui.dcFridgeSelector.currentText())
            number = str(self.ui.dcNumberSelector.currentText())

            name = fridge+' '+type+' '+number
            if type == 'Preamp':
                row = self.ui.dcDeviceTable.rowCount()
                self.ui.dcDeviceTable.insertRow(row)
                
                typeQ=QtGui.QTableWidgetItem(type)
                nameQ=QtGui.QTableWidgetItem(name)
                
                typeQ.property=(type,name)     
                nameQ.property=(type,name)
                
  
                self.ui.dcDeviceTable.setItem(row,0,typeQ)
                self.ui.dcDeviceTable.setItem(row,1,nameQ)
            
            else:
                gain = []
                gain.append(float(self.ui.channelAGain.text()))
                gain.append(float(self.ui.channelBGain.text()))
                gain.append(float(self.ui.channelCGain.text()))
                gain.append(float(self.ui.channelDGain.text()))
                
                row = self.ui.dcDeviceTable.rowCount()
                self.ui.dcDeviceTable.insertRow(row)  
                
                typeQ=QtGui.QTableWidgetItem(type)
                nameQ=QtGui.QTableWidgetItem(name)
                gainQ=QtGui.QTableWidgetItem(str(gain))
                
                typeQ.property=(type,name,(('gain',gain),))       
                nameQ.property=(type,name,(('gain',gain),))
                gainQ.property=(type,name,(('gain',gain),))
  
                self.ui.dcDeviceTable.setItem(row,0,typeQ)
                self.ui.dcDeviceTable.setItem(row,1,nameQ)
                self.ui.dcDeviceTable.setItem(row,2,gainQ)

        @QtCore.pyqtSlot()
        def on_sourceAddButton_released(self):  
            row = self.ui.uwaveSourceTable.rowCount()
            self.ui.uwaveSourceTable.insertRow(row)
            
            fridge = str(self.ui.sourceFridgeSelector.currentText())
            number = str(self.ui.sourceNumberSelector.currentText())

            if fridge=='DR Lab': fridge='DR'
            
            name = fridge+' GPIB Bus - GPIB1::'+number
            
            nameQ=QtGui.QTableWidgetItem(name)
            nameQ.property=('MicrowaveSource',name)
            self.ui.uwaveSourceTable.setItem(row,0,QtGui.QTableWidgetItem('MicrowaveSource'))
            self.ui.uwaveSourceTable.setItem(row,1,nameQ)
            
        @QtCore.pyqtSlot()
        def on_addDcCxnButton_released(self):  
            dcBoards = self.ui.dcDeviceTable.selectedItems()
            uwaveBoards = self.ui.uwaveDeviceTable.selectedItems()
            if len(dcBoards)==1 and len(uwaveBoards)==1:
                dcBoardName = self.ui.dcDeviceTable.item(self.ui.dcDeviceTable.row(dcBoards[0]),1)
                uwaveBoardName = self.ui.uwaveDeviceTable.item(self.ui.uwaveDeviceTable.row(uwaveBoards[0]),1)            
                row = self.ui.dcCxnTable.rowCount()
                self.ui.dcCxnTable.insertRow(row)
                dcTuple = (str(dcBoardName.text()),str(self.ui.channelSelect.currentText()))
                uwaveTuple = (str(uwaveBoardName.text()),str(self.ui.ioSelect.currentText()))

                dcBoardItem = QtGui.QTableWidgetItem(str(dcBoardName.text()))
                ioItem = QtGui.QTableWidgetItem(self.ui.ioSelect.currentText())
                uwaveBoardItem = QtGui.QTableWidgetItem(str(uwaveBoardName.text()))
                channelItem = QtGui.QTableWidgetItem(str(self.ui.channelSelect.currentText()))
                
                dcBoardItem.property = (uwaveTuple,dcTuple)
                ioItem.property = (uwaveTuple,dcTuple)
                uwaveBoardItem.property = (uwaveTuple,dcTuple)
                channelItem.property = (uwaveTuple,dcTuple)
                
                self.ui.dcCxnTable.setItem(row,3,channelItem)
                self.ui.dcCxnTable.setItem(row,2,dcBoardItem)
                self.ui.dcCxnTable.setItem(row,1,ioItem)
                self.ui.dcCxnTable.setItem(row,0,uwaveBoardItem)
                
        @QtCore.pyqtSlot()
        def on_addUwaveCxnButton_released(self):   
            boards = self.ui.uwaveDeviceTable.selectedItems()
            sources = self.ui.uwaveSourceTable.selectedItems()
            
            if len(boards)==1 and len(sources)==1:
                boardname = self.ui.uwaveDeviceTable.item(self.ui.uwaveDeviceTable.row(boards[0]),1)
                sourcename = self.ui.uwaveSourceTable.item(self.ui.uwaveSourceTable.row(sources[0]),1) #Regardless of column selected, use first column for name
                row = self.ui.uwaveCxnTable.rowCount()
                self.ui.uwaveCxnTable.insertRow(row)
                boarditem = QtGui.QTableWidgetItem(boardname.text())
                sourceitem = QtGui.QTableWidgetItem(sourcename.text())
                
                sourceitem.property = (str(boardname.text()),str(sourcename.text()))
                
                self.ui.uwaveCxnTable.setItem(row,1,sourceitem)
                self.ui.uwaveCxnTable.setItem(row,0,boarditem)
                
        @QtCore.pyqtSlot()
        def on_uwaveDeviceDelete_released(self):   
            ranges = self.ui.uwaveDeviceTable.selectedRanges()
            for rowrange in ranges:
                rowrange = sort(range(rowrange.topRow(),rowrange.bottomRow()+1))[::-1]
                for row in rowrange:
                    name = self.ui.uwaveDeviceTable.item(row,1)

                    uwaveCxns=self.ui.uwaveCxnTable.findItems(name.text(),QtCore.Qt.MatchExactly)
                    deletionRows=sort([self.ui.uwaveCxnTable.row(cxns) for cxns in uwaveCxns])[::-1]
                    for rows in deletionRows:
                        self.ui.uwaveCxnTable.removeRow(rows)
                        
                    dcCxns=self.ui.dcCxnTable.findItems(name.text(),QtCore.Qt.MatchExactly)
                    deletionRows=sort([self.ui.dcCxnTable.row(cxns) for cxns in dcCxns])[::-1]
                    for rows in deletionRows:
                        self.ui.dcCxnTable.removeRow(rows)

                    self.ui.uwaveDeviceTable.removeRow(row)
                
        @QtCore.pyqtSlot()
        def on_dcDeviceDelete_released(self):   
            ranges = self.ui.dcDeviceTable.selectedRanges()
            for rowrange in ranges:
                rowrange = sort(range(rowrange.topRow(),rowrange.bottomRow()+1))[::-1] #Delete the rows from last to first
                for row in rowrange:
                    name = self.ui.dcDeviceTable.item(row,1)
                    dcCxns=self.ui.dcCxnTable.findItems(name.text(),QtCore.Qt.MatchExactly)
                    deletionRows=sort([self.ui.dcCxnTable.row(cxns) for cxns in dcCxns])[::-1] #Delete all connections that use this device
                    
                    for rows in deletionRows:
                        self.ui.dcCxnTable.removeRow(rows)

                    self.ui.dcDeviceTable.removeRow(row)
                    
        @QtCore.pyqtSlot()
        def on_uwaveSourceDelete_released(self):   
            ranges = self.ui.uwaveSourceTable.selectedRanges()
            for rowrange in ranges:
                rowrange = sort(range(rowrange.topRow(),rowrange.bottomRow()+1))[::-1]
                for row in rowrange:
                    name = self.ui.uwaveSourceTable.item(row,1)
                    uwaveCxns=self.ui.uwaveCxnTable.findItems(name.text(),QtCore.Qt.MatchExactly)
                    deletionRows=sort([self.ui.uwaveCxnTable.row(cxns) for cxns in uwaveCxns])[::-1]
                    
                    for rows in deletionRows:
                        self.ui.uwaveCxnTable.removeRow(rows)
                        
                    self.ui.uwaveSourceTable.removeRow(row)   
                    
        @QtCore.pyqtSlot()
        def on_dcCxnDelete_released(self):   
            ranges = self.ui.dcCxnTable.selectedRanges()
            for rowrange in ranges:
                rowrange = sort(range(rowrange.topRow(),rowrange.bottomRow()+1))[::-1]
                for row in rowrange:
                    self.ui.dcCxnTable.removeRow(row)
                    
        @QtCore.pyqtSlot()
        def on_uwaveCxnDelete_released(self):   
            ranges = self.ui.uwaveCxnTable.selectedRanges()
            for rowrange in ranges:
                rowrange = sort(range(rowrange.topRow(),rowrange.bottomRow()+1))[::-1]
                for row in rowrange:
                    self.ui.uwaveCxnTable.removeRow(row)   
        @QtCore.pyqtSlot()
        def on_uwaveDeviceTable_cellClicked(self,i,j):
            print i,j
        
        def compileKey(self):
            devicesList = []
            dcCxnList = []
            uwaveCxnList = []
            for i in range(self.ui.uwaveDeviceTable.rowCount()):
                devicesList.append(self.ui.uwaveDeviceTable.item(i,1).property)
            for i in range(self.ui.dcDeviceTable.rowCount()):
                devicesList.append(self.ui.dcDeviceTable.item(i,0).property)
            for i in range(self.ui.uwaveSourceTable.rowCount()):
                devicesList.append(self.ui.uwaveSourceTable.item(i,1).property)   
            devicesTuple = tuple(devicesList)
            
            for i in range(self.ui.dcCxnTable.rowCount()):
                dcCxnList.append(self.ui.dcCxnTable.item(i,1).property)
                
            for i in range(self.ui.uwaveCxnTable.rowCount()):
                uwaveCxnList.append(self.ui.uwaveCxnTable.item(i,1).property)
            
            key = (devicesTuple,dcCxnList,uwaveCxnList)
            
            return key
            reg.cd(['','Servers','Qubit Server','Wiring'])
            reg.set(keyname,key)
            
        @QtCore.pyqtSlot()
        def on_writeKeyButton_released(self):  
            newKey = self.compileKey()  
            reg.cd(['','Servers','Qubit Server',wiringDir,'Backups'])
            backupKeyName = 'wiringBackup '+time.ctime()
            reg.set(backupKeyName,self.originalKey)

            reg.cd(['','Servers','Qubit Server',wiringDir])
            reg.set('wiring',newKey)
            self.originalKey = newKey
            
        @QtCore.pyqtSlot()
        def on_backupButton_released(self):  
            self.writeKey('wiringBackup')
            
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())