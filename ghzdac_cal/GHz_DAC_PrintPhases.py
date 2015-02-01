import labrad
import numpy as np
from matplotlib import pyplot
from matplotlib.patches import Rectangle
from matplotlib.collections import PatchCollection
import matplotlib
from matplotlib.cm import ScalarMappable as sm
    

DACS = ['A','B']
KEYS = ['lvdsMSD','lvdsMHD','lvdsSD','lvdsCheck','lvdsSuccess','fifoClockPolarity','fifoPHOF','fifoTries','fifoCounter','fifoSuccess','bistSuccess']

DIR = ['','Test','GHzFPGA','Vince DAC 11','130204']
NAME_PREFIX = 'FIFO3 SD'
TITLE = 'DAC 11'
PHASES = {(22.5,90):'22_90',
          (22.5,135):'22_135',
          (22.5,180):'22_180'}
PHASEOFFSET = 0
FAILLIMIT = .1
TIMELIMIT = .2
DIFFABTIMELIMIT = .3
SHOWFAIL = True

suptitleFont = {'fontsize':16}


def getFileData(dv,fileName):
    # Get file number for data with desired fileName
    files = dv.dir()[1]
    filenames = np.array([])
    filenums = np.array([])
    for file in files:
        filenames = np.append(filenames,file[8:])
        filenums = np.append(filenums,int(file[:5]))
    datanum = int(filenums[filenames==fileName][-1])
    
    # Open data set
    dv.open(datanum)
    data = np.array(dv.get())
    return data
    
    
def getDelaysProbs(dv, sd):
    filename = NAME_PREFIX + '%d' %sd
    allData  = getFileData(dv,filename)
    totalTrials = np.shape(allData)[0]
    fifoA = allData[:,10]
    bistA = allData[:,11]
    fifoB = allData[:,21]
    bistB = allData[:,22]
    fifoRateA = 1-np.sum(fifoA)/totalTrials
    bistRateA = 1-np.sum(bistA)/totalTrials
    fifoRateB = 1-np.sum(fifoB)/totalTrials
    bistRateB = 1-np.sum(bistB)/totalTrials
    phasesA = allData[:,23][np.logical_and(fifoA==1,bistA==1)]
    phasesB = allData[:,24][np.logical_and(fifoB==1,bistB==1)]
    phasesDiff = (allData[:,23] - allData[:,24])[np.all(np.array([fifoA==1,bistA==1,fifoB==1,bistB==1]),axis=0)]
    if np.size(phasesA) is 0:
        phaseBarA = None
    else:
        phaseBarA = [min(phasesA),max(phasesA)]
    if np.size(phasesB) is 0:
        phaseBarB = None
        phaseBarDiff = None
    else:
        phaseBarB = [min(phasesB),max(phasesB)]
        if np.size(phasesA) is 0:
            phaseBarDiff = None
        else:
            phaseBarDiff = [min(phasesDiff),max(phasesDiff)]
    phasesS = allData[:,25]
    successS = phasesS<750
    goodphasesS = phasesS[successS]
    if np.size(goodphasesS) is 0:
        phaseBarS = None
    else:
        phaseBarS = [min(goodphasesS),max(goodphasesS)]
    failRateS = 1-np.sum(successS)/float(totalTrials)
    
    return fifoRateA, bistRateA, phaseBarA, fifoRateB, bistRateB, phaseBarB, failRateS, phaseBarS, phaseBarDiff

    
def getOptimal(dv):
    filename = NAME_PREFIX + 'Optimal'
    allData = getFileData(dv,filename)
    msdA = np.unique(allData[:,1])
    mhdA = np.unique(allData[:,2])
    sdA = np.unique(allData[:,3])
    msdB = np.unique(allData[:,12])
    mhdB = np.unique(allData[:,13])
    sdB = np.unique(allData[:,14])
    return [msdA, mhdA, sdA, msdB, mhdB, sdB]
    
    
def xposition(phase1,phase2,phaseFlip):
    phase1list = np.array(sorted(np.unique(np.array(PHASES.keys())[:,0])))
    phase2list = np.array(sorted(np.unique(np.array(PHASES.keys())[:,1])))
    phase1order = int(np.where(phase1list==phase1)[0])
    phase2order = int(np.where(phase2list==phase2)[0])
    if phaseFlip:
        return phase2order*len(phase2list)+phase1order
    else:
        return phase1order*len(phase1list)+phase2order


def xlabels(phaseFlip):
    phase1list = sorted(np.unique(np.array(PHASES.keys())[:,0]))
    phase2list = sorted(np.unique(np.array(PHASES.keys())[:,1]))
    if phaseFlip:
        return [(int(ph1),int(ph2)) for ph2 in phase2list for ph1 in phase1list]
    else:
        return [(int(ph1),int(ph2)) for ph1 in phase1list for ph2 in phase2list]


def plotfunc(fig,subplot,data,title,colorScale=None,phaseFlip=False,sdMax=None):
    ax=fig.add_subplot(subplot[0],subplot[1],subplot[2])
    patches = []
    colors = []
    sds = []
    for datum in data:
        numpoints = len(datum)-2
        phase1, phase2 = datum[0] # ph1=0,22.5,45   ph2=0,45,90
        xval = xposition(phase1,phase2,phaseFlip)
        for count in range(numpoints):
            patches.append(Rectangle((xval-.25+(.5*count/numpoints),datum[1]-.25),0.5/numpoints,0.5))
            colors.append(datum[count+2])
            sds.append(datum[1])

    p = PatchCollection(patches, cmap=matplotlib.cm.jet, clim=colorScale)
    p.set_array(np.array(colors))
    ax.add_collection(p)
    fig.colorbar(p)
    if sdMax is not None:
        ax.axis([-.5,len(PHASES)-.5,-.5,sdMax+.5])
    else:
        ax.axis([-.5,len(PHASES)-.5,-.5,max(sds)+.5])
    ax.set_xticks(range(len(PHASES)))
    ax.set_xticklabels(xlabels(phaseFlip),rotation=90)
    if subplot[2]>((subplot[0]-1)*subplot[1]):ax.set_xlabel('FPGA Clock Phases (250MHz,1GHz)')
    if (subplot[2]%subplot[1]) is 1:ax.set_ylabel('LVDS SD')
    ax.set_title(title)
    

with labrad.connect() as cxn:
    dv=cxn.data_vault
    fig1 = pyplot.figure(1)
    pyplot.subplots_adjust(left=0.03, right=0.98, wspace=0.15, bottom=0.12, top=0.92, hspace=0.45)
    pyplot.suptitle(TITLE, **suptitleFont)
    fifoA, bistA, phaseA, fifoB, bistB, phaseB, failS, phaseS, phaseDiff, sdValues = [], [], [], [], [], [], [], [], [], []
    
    sdMax = 0
    for phases in PHASES.keys():
        dv.cd(DIR+[PHASES[phases]], True)
        print dv.dir()
        phase1 = phases[1] # 90, 135, 180
        phase2 = phases[0] # 0, 22.5, 45
        try:
            sdValues.append([phase1,phase2] + getOptimal(dv))
        except:
            pass
        for sd in range(16):
            try:
                print sd
                fifoRateA, bistRateA, phaseBarA, fifoRateB, bistRateB, phaseBarB, failRateS, phaseBarS, phaseBarDiff = getDelaysProbs(dv, sd)
                
                if phaseBarA is not None:
                    phaseDiffA = np.abs(phaseBarA[1]-phaseBarA[0])
                else:
                    phaseDiffA = 100
                if phaseBarB is not None:
                    phaseDiffB = np.abs(phaseBarB[1]-phaseBarB[0])
                else:
                    phaseDiffB = 100
                if phaseBarS is not None:
                    phaseDiffS = np.abs(phaseBarS[1]-phaseBarS[0])
                else:
                    phaseDiffS = 100
                if phaseBarDiff is not None:
                    phaseDiffDiff = np.abs(phaseBarDiff[1]-phaseBarDiff[0])
                else:
                    phaseDiffDiff = 100
                if (fifoRateA<=FAILLIMIT) and (bistRateA<=FAILLIMIT) and (fifoRateB<=FAILLIMIT) and (bistRateB<=FAILLIMIT) and (failRateS<=FAILLIMIT) and (phaseDiffA<=TIMELIMIT) and (phaseDiffB<=TIMELIMIT) and (phaseDiffS<=TIMELIMIT) and (phaseDiffDiff<=DIFFABTIMELIMIT):
                    fifoA.append([phases,sd,fifoRateA])
                    bistA.append([phases,sd,bistRateA])
                    fifoB.append([phases,sd,fifoRateB])
                    bistB.append([phases,sd,bistRateB])
                    failS.append([phases,sd,failRateS])
                    phaseA.append([phases,sd,phaseDiffA])
                    phaseB.append([phases,sd,phaseDiffB])
                    phaseS.append([phases,sd,phaseDiffS])
                    phaseDiff.append([phases,sd,phaseDiffDiff])
                elif SHOWFAIL:
                    if (fifoRateA>FAILLIMIT):
                        fifoA.append([phases,sd,100])
                    if (fifoRateB>FAILLIMIT):
                        fifoB.append([phases,sd,100])
                    if (bistRateA>FAILLIMIT):
                        bistA.append([phases,sd,100])
                    if (bistRateB>FAILLIMIT):
                        bistB.append([phases,sd,100])
                    if (failRateS>FAILLIMIT):
                        failS.append([phases,sd,100])
                    if (phaseDiffA>TIMELIMIT):
                        phaseA.append([phases,sd,100])
                    if (phaseDiffB>TIMELIMIT):
                        phaseB.append([phases,sd,100])
                    if (phaseDiffS>TIMELIMIT):
                        phaseS.append([phases,sd,100])
                    if (phaseDiffDiff>DIFFABTIMELIMIT):
                        phaseDiff.append([phases,sd,100])
                if sd > sdMax: sdMax = sd
            except:
                pass
    plotfunc(fig1,[3,3,1],bistA,'BIST A Failure Rate',(0,2*FAILLIMIT),False,sdMax)
    plotfunc(fig1,[3,3,2],fifoA,'FIFO A Failure Rate',(0,2*FAILLIMIT),False,sdMax)
    plotfunc(fig1,[3,3,3],phaseA,'(max-min)|Delay (ns) A wrt FPGA|',(0,2*TIMELIMIT),False,sdMax)
    plotfunc(fig1,[3,3,4],bistB,'BIST B Failure Rate',(0,2*FAILLIMIT),False,sdMax)
    plotfunc(fig1,[3,3,5],fifoB,'FIFO B Failure Rate',(0,2*FAILLIMIT),False,sdMax)
    plotfunc(fig1,[3,3,6],phaseB,'(max-min)|Delay (ns) B wrt FPGA|',(0,2*TIMELIMIT),False,sdMax)
    plotfunc(fig1,[3,3,7],phaseDiff,'(max-min)|Delay (ns) B wrt A|',(0,2*DIFFABTIMELIMIT),False,sdMax)
    plotfunc(fig1,[3,3,8],failS,'S3 Failure Rate',(0,2*FAILLIMIT),False,sdMax)
    plotfunc(fig1,[3,3,9],phaseS,'(max-min)|Delay (ns) S3 wrt FPGA|',(0,2*TIMELIMIT),False,sdMax)
    pyplot.show()