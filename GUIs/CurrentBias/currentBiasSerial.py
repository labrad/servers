import sys
import labrad
from PyQt4 import QtCore,QtGui,uic

with labrad.connect() as cxn:
    dc = cxn.dc_rack_server
    reg = cxn.registry
    


    class MainWindow (QtGui.QMainWindow):
        def __init__(self):
            QtGui.QMainWindow.__init__(self)
            ui_class, widget_class = uic.loadUiType("currentBiasSerial.ui")
            self.ui = ui_class()
            self.ui.setupUi(self)
            self.show()
            self.board = 'Null'
            reg.cd(['Servers','DC Racks','Links'])
            ThrowAway, DirList = reg.dir()
            self.ui.deviceSelect.insertItems(1,DirList)

        
        def setvoltage(self, channel, dac, slow, data):
            dc.channel_set_voltage(self.ui.cardAddress.value(), channel, dac, slow, data)

        @QtCore.pyqtSlot(str)
        def on_deviceSelect_currentIndexChanged(self, string):
            if self.ui.deviceSelect.currentIndex():
                dc.select_device(str(string))
            print string
                
        @QtCore.pyqtSlot()
        def on_deviceAddButton_released(self):
            print self.ui.deviceSelect.count()
            if not (self.ui.deviceNameAdder.text() == ""):
                self.ui.deviceSelect.insertItem(self.ui.deviceSelect.count()+1, str(self.ui.deviceNameAdder.text()))
            print self.ui.deviceNameAdder.text()
            print self.ui.deviceSelect.count()
                
            
        #Channel A Voltage Functions
        @QtCore.pyqtSlot()
        def on_fineCoarseSelectA_sliderReleased(self):
            setFineA = float(self.ui.fineSliderA.sliderPosition())/1000.0
            setCoarseA = float(self.ui.coarseSliderA.sliderPosition())/1000.0
            print self.ui.fineCoarseSelectA.sliderPosition()
            if self.ui.fineCoarseSelectA.sliderPosition():
                print 'coarse'
                self.setvoltage('A',1L,self.ui.fastSlowSelectA.sliderPosition(),setCoarseA)
            else:
                print 'fine'
                self.setvoltage('A',0L,self.ui.fastSlowSelectA.sliderPosition(),setFineA)
            
        @QtCore.pyqtSlot()
        def on_fineSliderA_sliderReleased(self):
            self.ui.fineBoxA.setValue(self.ui.fineSliderA.sliderPosition())
            setFineA = float(self.ui.fineSliderA.sliderPosition())/1000.0
            if not self.ui.fineCoarseSelectA.sliderPosition():
                self.setvoltage('A',0L,self.ui.fastSlowSelectA.sliderPosition(),setFineA)
            
        @QtCore.pyqtSlot()
        def on_coarseSliderA_sliderReleased(self):
            self.ui.coarseBoxA.setValue(self.ui.coarseSliderA.sliderPosition())
            setCoarseA = float(self.ui.coarseSliderA.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectA.sliderPosition():
                self.setvoltage('A',1L,self.ui.fastSlowSelectA.sliderPosition(),setCoarseA)   
        
        @QtCore.pyqtSlot(int)
        def on_fineBoxA_valueChanged(self, value):
            self.ui.fineSliderA.setValue(value)
            setFineA = float(value)/1000.0
            if not self.ui.fineCoarseSelectA.sliderPosition():
                self.setvoltage('A',0L,self.ui.fastSlowSelectA.sliderPosition(),setFineA) 

        @QtCore.pyqtSlot(int)
        def on_coarseBoxA_valueChanged(self, value):
            self.ui.coarseSliderA.setValue(self.ui.coarseBoxA.value())
            setCoarseA = float(value)/1000.0
            if self.ui.fineCoarseSelectA.sliderPosition():
                self.setvoltage('A',1L,self.ui.fastSlowSelectA.sliderPosition(),setCoarseA)                    
                
        @QtCore.pyqtSlot()
        def on_pushButtonA_clicked(self):
            dc.channel_stream(self.ui.cardAddress.value(), 'A')
            
        #Channel B Voltage Functions    
        @QtCore.pyqtSlot()
        def on_fineCoarseSelectB_sliderReleased(self):
            setFineB = float(self.ui.fineSliderB.sliderPosition())/1000.0
            setCoarseB = float(self.ui.coarseSliderB.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectB.sliderPosition():
                self.setvoltage('B',1L,self.ui.fastSlowSelectB.sliderPosition(),setCoarseB)
            else:
                self.setvoltage('B',0L,self.ui.fastSlowSelectB.sliderPosition(),setFineB)
            
        @QtCore.pyqtSlot()
        def on_fineSliderB_sliderReleased(self):
            self.ui.fineBoxB.setValue(self.ui.fineSliderB.sliderPosition())
            setFineB = float(self.ui.fineSliderB.sliderPosition())/1000.0
            if not self.ui.fineCoarseSelectB.sliderPosition():
                self.setvoltage('B',0L,self.ui.fastSlowSelectB.sliderPosition(),setFineB)
            
        @QtCore.pyqtSlot()
        def on_coarseSliderB_sliderReleased(self):
            self.ui.coarseBoxB.setValue(self.ui.coarseSliderB.sliderPosition())
            setCoarseB = float(self.ui.coarseSliderB.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectB.sliderPosition():
                self.setvoltage('B',1L,self.ui.fastSlowSelectB.sliderPosition(),setCoarseB) 
        
        @QtCore.pyqtSlot(int)
        def on_fineBoxB_valueChanged(self, value):
            self.ui.fineSliderB.setValue(value)
            setFineB = float(value)/1000.0
            if not self.ui.fineCoarseSelectB.sliderPosition():
                self.setvoltage('B',0L,self.ui.fastSlowSelectB.sliderPosition(),setFineB) 

        @QtCore.pyqtSlot(int)
        def on_coarseBoxB_valueChanged(self, value):
            self.ui.coarseSliderB.setValue(self.ui.coarseBoxD.value())
            setCoarseB = float(value)/1000.0
            if self.ui.fineCoarseSelectB.sliderPosition():
                self.setvoltage('B',1L,self.ui.fastSlowSelectD.sliderPosition(),setCoarseB)         
                
        @QtCore.pyqtSlot()
        def on_pushButtonB_clicked(self):
            dc.channel_stream(self.ui.cardAddress.value(), 'B')
            
        #Channel C Voltage Functions    
        @QtCore.pyqtSlot()
        def on_fineCoarseSelectC_sliderReleased(self):
            setFineC = float(self.ui.fineSliderC.sliderPosition())/1000.0
            setCoarseC = float(self.ui.coarseSliderC.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectC.sliderPosition():
                self.setvoltage('C',1L,self.ui.fastSlowSelectC.sliderPosition(),setCoarseC)
            else:
                self.setvoltage('C',0L,self.ui.fastSlowSelectC.sliderPosition(),setFineC)
            
        @QtCore.pyqtSlot()
        def on_fineSliderC_sliderReleased(self):
            self.ui.fineBoxC.setValue(self.ui.fineSliderC.sliderPosition())
            setFineC = float(self.ui.fineSliderC.sliderPosition())/1000.0
            if not self.ui.fineCoarseSelectC.sliderPosition():
                self.setvoltage('C',0L,self.ui.fastSlowSelectC.sliderPosition(),setFineC)
                print 'fine'
            
        @QtCore.pyqtSlot()
        def on_coarseSliderC_sliderReleased(self):
            self.ui.coarseBoxC.setValue(self.ui.coarseSliderC.sliderPosition())
            setCoarseC = float(self.ui.coarseSliderC.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectC.sliderPosition():
                self.setvoltage('C',1L,self.ui.fastSlowSelectC.sliderPosition(),setCoarseC)        
  
        @QtCore.pyqtSlot(int)
        def on_fineBoxC_valueChanged(self, value):
            self.ui.fineSliderC.setValue(value)
            setFineC = float(value)/1000.0
            if not self.ui.fineCoarseSelectC.sliderPosition():
                self.setvoltage('C',0L,self.ui.fastSlowSelectC.sliderPosition(),setFineC) 

        @QtCore.pyqtSlot(int)
        def on_coarseBoxC_valueChanged(self, value):
            self.ui.coarseSliderC.setValue(self.ui.coarseBoxC.value())
            setCoarseC = float(value)/1000.0
            if self.ui.fineCoarseSelectC.sliderPosition():
                self.setvoltage('C',1L,self.ui.fastSlowSelectC.sliderPosition(),setCoarseC)        

        @QtCore.pyqtSlot()
        def on_pushButtonC_clicked(self):
            dc.channel_stream(self.ui.cardAddress.value(), 'C')
            
        #Channel D Voltage Functions    
        @QtCore.pyqtSlot()
        def on_fineCoarseSelectD_sliderReleased(self):
            setFineD = float(self.ui.fineSliderD.sliderPosition())/1000.0
            setCoarseD = float(self.ui.coarseSliderD.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectD.sliderPosition():
                self.setvoltage('D',1L,self.ui.fastSlowSelectD.sliderPosition(),setCoarseD)
            else:
                self.setvoltage('D',0L,self.ui.fastSlowSelectD.sliderPosition(),setFineD)
            
        @QtCore.pyqtSlot()
        def on_fineSliderD_sliderReleased(self):
            self.ui.fineBoxD.setValue(self.ui.fineSliderD.sliderPosition())
            setFineD = float(self.ui.fineSliderD.sliderPosition())/1000.0
            if not self.ui.fineCoarseSelectD.sliderPosition():
                self.setvoltage('D',0L,self.ui.fastSlowSelectC.sliderPosition(),setFineD)
            
        @QtCore.pyqtSlot()
        def on_coarseSliderD_sliderReleased(self):
            self.ui.coarseBoxD.setValue(self.ui.coarseSliderD.sliderPosition())
            setCoarseD = float(self.ui.coarseSliderD.sliderPosition())/1000.0
            if self.ui.fineCoarseSelectD.sliderPosition():
                self.setvoltage('D',1L,self.ui.fastSlowSelectD.sliderPosition(),setCoarseD)      

        @QtCore.pyqtSlot(int)
        def on_fineBoxD_valueChanged(self, value):
            self.ui.fineSliderD.setValue(value)
            setFineD = float(value)/1000.0
            if not self.ui.fineCoarseSelectD.sliderPosition():
                self.setvoltage('D',0L,self.ui.fastSlowSelectD.sliderPosition(),setFineD) 

        @QtCore.pyqtSlot(int)
        def on_coarseBoxD_valueChanged(self, value):
            self.ui.coarseSliderD.setValue(self.ui.coarseBoxD.value())
            setCoarseD = float(value)/1000.0
            if self.ui.fineCoarseSelectD.sliderPosition():
                self.setvoltage('D',1L,self.ui.fastSlowSelectD.sliderPosition(),setCoarseD)          
        
        @QtCore.pyqtSlot()
        def on_pushButtonD_clicked(self):
            dc.channel_stream(self.ui.cardAddress.value(), 'D')
            
    app = QtGui.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
        