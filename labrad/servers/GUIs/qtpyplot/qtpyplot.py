"""
PyQt4-matplotlib integration gleefully stolen from:
Eli Bendersky (eliben@gmail.com)
--Josh Mutus,2013
"""
import sys, os, random
from PyQt4.QtCore import *
from PyQt4.QtGui import *
sys.path.insert(0, 'C:\\labrad\\dev\\pyle')
import matplotlib
from pylab import plot, show
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np
import time
from pyle.datavault import DataVaultWrapper


import labrad

def convertForImshow(args,sec=0):
    '''
    Converts colormap data from the datavault into something plt.imshow 
    can plot. Returns an array that imshow will plot.    
    '''
    reverse = False
    arrRev = np.copy(args)
    # print args
    if args[:,0][0]==args[:,0][1]: #Checks if the first column is the one that repeats
        print "check"
        # print args[:,0],args[:,1]
        args[:,0]=arrRev[:,1]
        args[:,1]=arrRev[:,0]
        reverse=True
    # print args
    x,y = np.copy(np.unique(args[:,0])).size,np.copy(np.unique(args[:,1])).size #Find size of array
    
    # arr=np.zeros((y.size,x.size))
    # print "dimensions: ",arr.shape
    # print arr.shape
    # print args[:,1+sec].size
    j=0
    arr = np.copy(args[:,2].reshape(y,x))
    # for i, value in enumerate(args[:,2+sec]):
        # row, col= np.argwhere(args==value)[0][0],np.argwhere(args==value)[0][1]
        # ent = np.argwhere(args==value)[0][0]
        # xEnt,yEnt = args[:,0][ent],args[:,1][ent]
        # row,col= np.argwhere(x==xEnt)[0][0],np.argwhere(y==yEnt)[0][0]
        
        # print row,col
        # print col, row
        # arr[col][row] = value
    
    # for n in range(y):
        # for m in range(x):          
            # arr[n][m] = args[:,2+sec][j]
            # j=j+1
    arr = arr[::-1]
    if reverse:
        arr=arr.T
        arr = arr[::-1]
    return arr
    
class DepListWidget(QListWidget):
    def __init__(self, parent=None):
        super(MyListWidget, self).__init__(parent)
        self.itemClicked.connect(self.on_item_clicked)

    def mousePressEvent(self, event):
        self._mouse_button = event.button()
        super(MyListWidget, self).mousePressEvent(event)

    def on_item_clicked(self, item):
        print item.text(), self._mouse_button
    

class AppForm(QMainWindow):
    ## making a new signal
    new_signal = pyqtSignal()
    def __init__(self, parent=None):
        self.cxn = labrad.connect()
        self.dv = self.cxn.data_vault 
        self.path = ['']
        # self.path = ['','Ted','Paramp','UCSB4.2','dev4.2.4','131010']
        QMainWindow.__init__(self, parent)
        self.setWindowTitle('QtPyPlot')
        #Stuff for importing from datavault
        self.plotShow = 1
        self.plotEnd = 5
        self.subMem = False #Do I subtract memory trace from current trace?
        self.showMem = False #Do I show the memory trace?
        self.buffTrace = np.array([]) #array to store trace
        self.listDep=[]
        self.plots = np.arange(self.plotShow,self.plotEnd,1)
        self.myData = DataVaultWrapper(self.path,self.cxn)
        # self.populate_browserList()
        self.dirList = self.myData.dir()
        # self.dirList.insert(0,'...')
        self.dep = 0
        # self.plotList = ['...']+self.myData.keys()
        self.plotList = self.myData.keys()
        # print self.plotList
        # for ps in self.plots:
            # print "enqueue " + str(ps)
            # self.myData.enqueueId(int(ps))
        # while not self.myData.cache.cache: 
            # print "Loading..."
            # time.sleep(1)
        ### end of stuff for importing form datavault

        self.create_menu()
        self.create_main_frame()
        # self.create_status_bar()


        self.textbox.setText(str(self.path))
        self.on_draw()

    def save_plot(self):
        file_choices = "PNG (*.png)|*.png"
        
        path = unicode(QFileDialog.getSaveFileName(self, 
                        'Save file', '', 
                        file_choices))
        if path:
            self.canvas.print_figure(path, dpi=self.dpi)
            self.statusBar().showMessage('Saved to %s' % path, 2000)
    def print_plot(self):
        dialog = QPrintDialog()
        # if dialog.exec_() == QDialog.Accepted:
        self.goPrinter()
            # self.canvas.print_figure(os.getcwd()+'temp.png',dpi=self.dpi).print_(dialog.printer())
            # self.canvas.document().print_(dialog.printer())
    def goPrinter(self):
        printer = QPrinter()
        printer.Letter
        printer.HighResolution
        printer.Color
        
        anotherWidget= QPrintDialog(printer,self)
        if(anotherWidget.exec_() != QDialog.Accepted):
            return
        p = QPixmap.grabWidget(self.canvas)
        printLabel = QLabel()
        printLabel.setPixmap(p)
        painter = QPainter(printer)
        printLabel.render(painter)
        painter.end()

        show()
    def on_about(self):
        msg = """ A demo of using PyQt with matplotlib:
        
         * Use the matplotlib navigation bar
         * Add values to the text box and press Enter (or click "Draw")
         * Show or hide the grid
         * Drag the slider to modify the width of the bars
         * Save the plot to a file using the File menu
         * Click on a bar to receive an informative message
        """
        QMessageBox.about(self, "About the demo", msg.strip())
    
    def on_pick(self, event):
        # The event received here is of the type
        # matplotlib.backend_bases.PickEvent
        #
        # It carries lots of information, of which we're using
        # only a small amount here.
        # 
        box_points = event.artist.get_bbox().get_points()
        msg = "You've clicked on a bar with coords:\n %s" % box_points
        
        QMessageBox.information(self, "Click!", msg)
    # def add_plot(self):
        # arr = self.myData[self.plotShow]
        # self.axes.plot(arr[:,0],arr[:,2+self.dep])
        # print "add plot"
    def on_draw(self):
        """ Redraws the figure
        """
        # str = unicode(self.textbox.text())
        # self.data = map(int, str.split())
        arr = self.myData[self.plotShow]
        # x = range(len(self.data))
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)
        # self.axes.clear()  
        self.axes.set_title(arr.name)
        self.setWindowTitle('QtPyPlot: '+str(self.plotShow))
        if len(arr.indep) == 2:
            indep0First = np.unique(arr[:,0])[0]
            indep0Last = np.unique(arr[:,0])[-1]
            indep1First = np.unique(arr[:,1])[0]
            indep1Last = np.unique(arr[:,1])[-1]
            ratio = (indep0Last - indep0First)/(indep1Last - indep1First)
            x = convertForImshow(self.myData[self.plotShow],sec= self.dep)
            # clear the axes and redraw the plot anew
            #
                  
            self.axes.grid(self.grid_cb.isChecked())
            
            implt= self.axes.imshow(x,aspect=ratio,extent=[indep0First,indep0Last,indep1First,indep1Last])
            # implt.set_clim(0,30)
            self.axes.set_xlabel(arr.indep[0][0]+' ('+arr.indep[0][1]+')')
            self.axes.set_ylabel(arr.indep[1][0]+' ('+arr.indep[0][1]+')')
            self.cbar = self.fig.colorbar(implt)
        else:
            if self.subMem:
                   arr[:,1] = arr[:,1]-self.buffTrace[:,1]
            for ent in self.listDep:

                indep0First = np.unique(arr[:,0])[0]
                indep0Last = np.unique(arr[:,0])[-1]
                dep0First = np.unique(arr[:,1+ent])[0]
                dep0Last = np.unique(arr[:,1+ent])[-1]
                self.axes.set_xlabel(arr.indep[0][0]+' ('+arr.indep[0][1]+')')
                self.axes.set_ylabel(arr.dep[0+ent][0]+' ('+arr.dep[0+ent][1]+')')
                # if not self.subMem:
                    # self.axes.plot(arr[:,0],arr[:,1+ent])
                self.axes.plot(arr[:,0],arr[:,1+ent])
                if self.showMem:
                    self.axes.plot(self.buffTrace[:,0],self.buffTrace[:,1])
                # if self.subMem:
                    # self.axes.plot(arr[:,0],arr[:,1+ent]-self.buffTrace[:,1])
                
            # self.axes.axis([indep0First, indep0Last,dep0First,dep0Last])
        self.canvas.draw()
    def on_next(self):
        self.plotShow=self.plotShow+1
        print self.plotShow
        self.on_draw()  
        self.update_dep_list()        
    def on_prev(self):
        if self.plotShow>1:
            self.plotShow=self.plotShow-1
            self.on_draw()
        print self.plotShow
        self.update_dep_list()
    def on_save_trace(self): 
        self.buffTrace = np.array([]) #re-initialize to empty, then add trace
        self.buffTrace = np.vstack( (self.myData[self.plotShow][:,0].copy(),self.myData[self.plotShow][:,1+self.listDep[0]].copy()))
        self.buffTrace = self.buffTrace.T
        # print "Trace buffered: ", self.buffTrace[:,0], self.buffTrace[:,1]
    def on_sub_trace(self):
        self.subMem= True
        self.on_draw()
        self.subMem=False
    def on_plot_mem(self):
        self.showMem= True
        self.on_draw()
        self.showMem=False
    def on_browser_list(self,item):
        print str(item.text())
        # strItem = str(item.text())
        # numItem = [int(s) for s in strItem.split() if s.isdigit()]
        # print numItem
        # if item.text()=='[...]' and len(self.path)>1:
        if item.text()=='...' and len(self.path)>1:
            self.path.pop()
            print self.path
            self.update_browse_list()
            self.depList.clear()
        # elif len(self.path)==1:
            # pass
        # else
        elif item.text() in self.plotList:
            # self.plotShow =  self.myData.keys().index(item.text())+1
            self.plotShow =  int(str.split(str(item.text()))[0])
            print self.plotShow
            self.update_dep_list()
            self.dep = 0
            self.listDep = [] #re-initialize list of deps
            self.on_draw()
            
        elif str(item.text()) in self.dirList:
            print "It's a DEER"
            self.path= self.path + [str(item.text())]
            print self.path
            self.update_browse_list()
            
        # print self.plotShow
    def on_dep_list(self,item):    
        # print item.checkState()
        # If item is checked, that means it was changed from unchecked, which means is has to be 
        # added to the array
        prop1, prop2 = str(item.text()).split(' vs. ')[0].split(';')[0],str(item.text()).split(' vs. ')[0].split(';')[1]
        # print prop1,prop2
        for ind, ent in enumerate(self.myData[self.plotShow].dep):
            if prop1 in ent:
                if prop2 in ent:
                    self.dep = ind
                    # print "the dep is: ", ind
                    if item.checkState() == 2:
                        self.listDep.append(ind)
                    if item.checkState() == 0:
                        self.listDep.remove(ind)
                    print "list of deps ", self.listDep
                    self.on_draw()
                            
         
            # Item has gone to unchecked, need to be removed from 
        # print item(index)
        # dep =  str.split(str(item.text()))[0]
    def on_dep_active(self, item):
        print "item selection changed " +item.text()
    def new_func(self):
        print "new signal rec'd"
    def create_main_frame(self):
        self.main_frame = QWidget()
        
        # Create the mpl Figure and FigCanvas objects. 
        # 5x4 inches, 100 dots-per-inch
        #
        self.dpi = 100
        self.fig = Figure((5.0, 4.0), dpi=self.dpi)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self.main_frame)
        
        # Since we have only one plot, we can use add_axes 
        # instead of add_subplot, but then the subplot
        # configuration tool in the navigation toolbar wouldn't
        # work.
        #
        # self.axes = self.fig.add_subplot(111)
        
        # Bind the 'pick' event for clicking on one of the bars
        #
        self.canvas.mpl_connect('pick_event', self.on_pick)
        
        # Create the navigation toolbar, tied to the canvas
        #
        self.mpl_toolbar = NavigationToolbar(self.canvas, self.main_frame)
        
        # Other GUI controls
        # 
        self.textbox = QLineEdit()
        self.textbox.setMinimumWidth(200)
        self.connect(self.textbox, SIGNAL('editingFinished ()'), self.on_draw)
        

        
        self.prev_button = QPushButton("&Prev")
        self.connect(self.prev_button, SIGNAL('clicked()'), self.on_prev)
        
        self.next_button = QPushButton("&Next")
        self.connect(self.next_button, SIGNAL('clicked()'), self.on_next)
        
        # Trace memory operations
        #
        self.save_button = QPushButton("Trace->Mem")
        self.connect(self.save_button, SIGNAL('clicked()'), self.on_save_trace)
        
        self.plot_mem_button = QPushButton("&Show Mem")
        self.connect(self.plot_mem_button, SIGNAL('clicked()'), self.on_plot_mem)
        
        self.sub_button = QPushButton("&Trace - Mem")
        self.connect(self.sub_button, SIGNAL('clicked()'), self.on_sub_trace)
        
        
        self.grid_cb = QCheckBox("Show &Grid")
        self.grid_cb.setChecked(False)
        self.connect(self.grid_cb, SIGNAL('stateChanged(int)'), self.on_draw)
        
        # slider_label = QLabel('Bar width (%):')
        # self.slider = QSlider(Qt.Horizontal)
        # self.slider.setRange(1, 100)
        # self.slider.setValue(20)
        # self.slider.setTracking(True)
        # self.slider.setTickPosition(QSlider.TicksBothSides)
        # self.connect(self.slider, SIGNAL('valueChanged(int)'), self.on_draw)
        #
        # Make the list of files in the dataVault directory
        #
        self.browserList = QListWidget()
        self.browserList.setMinimumWidth(350)
        self.depList = QListWidget()
        self.depList.setMinimumWidth(100)
        
        
        # self.browserList.setMinimumWidth(300)
        self.populate_browserList()
        # for entry in self.plotList:
            # self.browserList.addItem(entry)
        self.connect(self.browserList,SIGNAL("itemDoubleClicked(QListWidgetItem*)"),self.on_browser_list)
        # self.connect(self.depList,SIGNAL("itemClicked(QListWidgetItem*)"),self.on_dep_list)
        self.connect(self.depList,SIGNAL("itemChanged(QListWidgetItem*)"),self.on_dep_list)
        # self.connect(self.depList,SIGNAL("itemClicked(QListWidgetItem*)"),self.on_dep_active)
 
        #
        # Layout with box sizers
        # 
        hbox = QHBoxLayout()
        hboxmem  = QHBoxLayout()
        hboxPrime = QHBoxLayout()
        
        for w in [  self.textbox,  self.prev_button, self.next_button]:
            hbox.addWidget(w)
            hbox.setAlignment(w, Qt.AlignVCenter)
        for w in [self.save_button,self.sub_button,self.plot_mem_button]:
            hboxmem.addWidget(w)
            hboxmem.setAlignment(w, Qt.AlignVCenter)
            
        vbox = QVBoxLayout()
        # vbox.addWidget(self.browserList)
        vbox.addWidget(self.canvas)
        vbox.addWidget(self.mpl_toolbar)
        vbox.addLayout(hbox)
        vbox.addLayout(hboxmem)
        hboxPrime.addLayout(vbox)
        hboxPrime.addWidget(self.browserList)
        hboxPrime.addWidget(self.depList)
        
        self.main_frame.setLayout(hboxPrime)
        self.setCentralWidget(self.main_frame)
        
        # Defining some new signals
        self.new_signal.connect(self.new_func)
    def mousePressEvent(self,event):
        self.new_signal.emit()
        if event.button()==Qt.RightButton:
             print "the right mouse button was pressed.. somewhere"
    # def create_status_bar(self):
        # self.status_text = QLabel("We can write some status here")
        # self.statusBar().addWidget(self.status_text, 1)
        
    def create_menu(self):        
        self.file_menu = self.menuBar().addMenu("&File")
        
        load_file_action = self.create_action("&Save plot",
            shortcut="Ctrl+S", slot=self.save_plot, 
            tip="Save the plot")
        print_action = self.create_action("&Print plot", 
            slot=self.print_plot, tip="Print the plot")
        quit_action = self.create_action("&Quit", slot=self.close, 
            shortcut="Ctrl+Q", tip="Close the application")
        
        self.add_actions(self.file_menu, 
            (load_file_action,print_action, None, quit_action))
        
        self.help_menu = self.menuBar().addMenu("&Help")
        about_action = self.create_action("&About", 
            shortcut='F1', slot=self.on_about, 
            tip='About the demo')
        
        self.add_actions(self.help_menu, (about_action,))

    def add_actions(self, target, actions):
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)

    def update_browse_list(self):
        self.textbox.setText(str(self.path))
        self.myData = DataVaultWrapper(self.path,self.cxn)
        self.dirList = self.myData.dir()
        if len(self.path)>1:
            self.dirList.insert(0,'...')
        self.plotList = self.myData.keys()
        self.populate_browserList()
        print "dirList  =",self.dirList
    def update_dep_list(self): 
        self.depList.clear()
        for entry in self.myData[self.plotShow].dep:
            title = entry[0]+ ';' +  entry[1]+ ' vs. ' + self.myData[self.plotShow].indep[0][0]
            itm = QListWidgetItem(title)
            itm.setCheckState(False)
            # print title
            self.depList.addItem(itm)
    def populate_browserList(self):
        self.browserList.clear()
        for entry in self.dirList:
            itm = QListWidgetItem(entry)
            itm.setIcon(QIcon('tick.png'))
            self.browserList.addItem(itm)
        for entry in self.plotList:
            self.browserList.addItem(entry)
        self.browserList.update()

    
    def create_action(  self, text, slot=None, shortcut=None, 
                        icon=None, tip=None, checkable=False, 
                        signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action



def main():
    app = QApplication(sys.argv)
    form = AppForm()
    form.show()
    app.exec_()


if __name__ == "__main__":
    main()
