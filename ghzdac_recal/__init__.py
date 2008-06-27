# Copyright (C) 2007-2008  Max Hofheinz 
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from correction import DACcorrection, IQcorrection, \
     cosinefilter, gaussfilter, flatfilter
from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.thread import blockingCallFromThread as block, startReactor
import labrad

from numpy import shape, array, size
SETUPTYPESTRINGS = ['no IQ mixer', \
                    'DAC A -> mixer I, DAC B -> mixer Q',\
                    'DAC A -> mixer Q, DAC B -> mixer I']
SESSIONNAME = 'GHzDAC recalibration test'
ZERONAME = 'zero'
PULSENAME = 'pulse'
IQNAME = 'IQ'
CHANNELNAMES = ['DAC A','DAC B']

@inlineCallbacks
def getDataSets(cxn, boardname, caltype, errorClass=None):
    reg = cxn.registry
    ds = cxn.data_vault
    yield reg.cd(['',SESSIONNAME,boardname],True)
    if caltype in (yield reg.dir())[1]:
        calfiles = (yield reg.get(caltype))
    else:
        calfiles = array([])
    
    if not size(calfiles):
        if errorClass:
            raise errorClass(caltype)
        elif errorClass != 'quiet':
            print 'Warning: No %s calibration loaded.' % caltype
            print '         No %s correction will be performed.' % caltype
    returnValue(calfiles)
    


@inlineCallbacks
def IQcorrectorAsync(fpganame, connection,
                     zerocor = True, pulsecor = True, iqcor = True,
                     lowpass = cosinefilter, bandwidth = 0.4, errorClass = None):

    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.connect argument
    """
    if connection:
        cxn = connection
    else:
        cxn = yield labrad.connectAsync()
        
    ds=cxn.data_vault
    ctx = ds.context()

    yield ds.cd(['',SESSIONNAME,fpganame],context=ctx)

    corrector = IQcorrection(fpganame, lowpass, bandwidth)

    # Load Zero Calibration
    if zerocor:
        datasets = yield getDataSets(cxn, fpganame, ZERONAME, errorClass)
        for dataset in datasets:
            filename = yield ds.open(dataset,context=ctx)
            print 'Loading zero calibration from %s:' % filename[1]
            datapoints = (yield ds.get(context=ctx)).asarray
            corrector.loadZeroCal(datapoints, dataset)
            
    

    #Load pulse response
    if pulsecor:
        dataset = yield getDataSets(cxn, fpganame, PULSENAME, errorClass)
        if dataset != []:
            dataset = dataset[0]
            filename = yield ds.open(dataset,context=ctx)
            print 'Loading pulse calibration from %s:' % filename[1]
            setupType = yield ds.get_parameter('Setup type',context=ctx)
            print '  %s' % setupType
            IisB = (setupType == SETUPTYPESTRINGS[2])
            datapoints = (yield ds.get(context=ctx)).asarray
            carrierfreq = (yield ds.get_parameter('Anritsu frequency',
                                                  context=ctx))['GHz']
            corrector.loadPulseCal(datapoints, carrierfreq, IisB)
 

    # Load Sideband Calibration
    if iqcor:
        datasets = yield getDataSets(cxn, fpganame, IQNAME, errorClass)
        for dataset in datasets:
            filename = yield ds.open(dataset,context=ctx)
            print 'Loading sideband calibration from %s:' % filename[1]
            sidebandStep = \
                (yield ds.get_parameter('Sideband frequency step',
                                        context=ctx))['GHz']
            sidebandCount = \
                yield ds.get_parameter('Number of sideband frequencies',
                                        context=ctx)
            datapoints = (yield ds.get(context=ctx)).asarray
            corrector.loadSidebandCal(datapoints, sidebandStep, dataset)

    if not connection:
        yield cxn.disconnect()

    returnValue(corrector)


def IQcorrector(fpganame, 
                zerocor = True, pulsecor = True, iqcor = True,
                lowpass = cosinefilter, bandwidth = 0.4):
    startReactor()
    corrector = block(IQcorrectorAsync, fpganame, None, zerocor,
                      pulsecor, iqcor, lowpass, bandwidth)
    corrector.recalibrationRoutine = recalibrate
    return corrector





@inlineCallbacks
def DACcorrectorAsync(fpganame, channel, connection = None, \
                      lowpass = gaussfilter, bandwidth = 0.13, errorClass = None):

    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.connect argument
    """
    if connection:
        cxn = connection
    else:
        cxn = yield labrad.connectAsync()

    ds=cxn.data_vault
    ctx = ds.context()

    yield ds.cd(['',SESSIONNAME,fpganame],context=ctx)

    corrector = DACcorrection(fpganame, lowpass, bandwidth)

    if not isinstance(channel, str):
        channel = CHANNELNAMES[channel]

    dataset = yield getDataSets(cxn, fpganame, channel, errorClass)
    if dataset != []:
        dataset = dataset[0]
        yield ds.open(dataset, context=ctx)
        datapoints = (yield ds.get(context=ctx)).asarray
        corrector.loadCal(datapoints)
    if not connection:
        yield cxn.disconnect()
        
    returnValue(corrector)


def DACcorrector(fpganame, channel, \
                 lowpass = gaussfilter, bandwidth = 0.13):

    startReactor()
    return block(DACcorrectorAsync, fpganame, channel, None,
                 lowpass, bandwidth)

import calibrate

    

@inlineCallbacks
def recalibrateAsync(boardname, carrierMin, carrierMax, zeroCarrierStep=0.025,
                sidebandCarrierStep=0.05, sidebandMax=0.35, sidebandStep=0.05,
                corrector=None):
    cxn = yield labrad.connectAsync()
    ds = cxn.data_vault
    reg = cxn.registry
    reg.cd(['', SESSIONNAME, boardname])
    anritsuID = yield reg.get('Anritsu ID')
    anritsuPower = (yield reg.get('Anritsu Power'))['dBm']
    if corrector is None:
        corrector = yield IQcorrectorAsync(boardname, cxn)
    if corrector.board != boardname:
        print 'Provided corrector is not for %s.' % boardname
        print 'Loading new corrector. Provided corrector will not be updated.'
        corrector = yield IQcorrectorAsync(boardname, cxn)
    
    if zeroCarrierStep is not None:
        #check if a corrector has been provided and if it is up to date
        #or if we have to load a new one.
        if corrector.zeroCalFiles != \
          (yield getDataSets(cxn, boardname, ZERONAME, 'quiet')):
            print 'Provided correcetor is outdated.'
            print 'Loading new corrector. Provided corrector will not be updated.'
            corrector = yield IQcorrectorAsync(boardname, cxn)
  
        # do the zero calibration
        dataset = calibrate.zeroScanCarrier(cxn,
                                     {'carrrierMin': carrierMin,
                                      'carrierMax': carrierMax,
                                      'carrierStep': zeroCarrierStep,
                                      'anritsu dBm': anritsuPower},
                                     boardname)
        # load it into the corrector
        yield ds.open(dataset)
        datapoints = (yield ds.get()).asarray
        corrector.loadZeroCal(datapoints, dataset)
        # eliminate obsolete zero calibrations
        datasets = corrector.eliminateZeroCals()
        # and save which ones are being used now
        yield reg.cd(['',SESSIONNAME,boardname],True)
        yield reg.set(ZERONAME, datasets)
    if sidebandCarrierStep is not None:
        #check if a corrector has been provided and if it is up to date
        #or if we have to load a new one.
        if (corrector.sidebandCalFiles != \
          (yield getDataSets(cxn, boardname, IQNAME, 'quiet'))) or \
          (array([corrector.pulseCalFile]) != \
               (yield getDataSets(cxn, boardname, PULSENAME, 'quiet'))):
            print 'Provided correcetor is outdated.'
            print 'Loading new corrector. Provided corrector will not be updated.'
            corrector = yield IQcorrectorAsync(boardname, cxn)

            
        # do the pulse calibration
        dataset = calibrate.sidebandScanCarrier(cxn,
                                     {'carrrierMin': carrierMin,
                                      'carrierMax': carrierMax,
                                      'carrierStep': sidebandCarrierStep,
                                      'anritsu dBm': anritsuPower},
                                     boardname, corrector)
        # load it into the corrector
        yield ds.open(dataset)
        sidebandStep = \
            (yield ds.get_parameter('Sideband frequency step'))['GHz']
        sidebandCount = \
            yield ds.get_parameter('Number of sideband frequencies')
        datapoints = (yield ds.get()).asarray
        corrector.loadSidebandCal(datapoints, sidebandStep, dataset)
        # eliminate obsolete zero calibrations
        datasets = corrector.eliminateSidebandCals()
        # and save which ones are being used now
        yield reg.cd(['',SESSIONNAME,boardname],True)
        yield reg.set(IQNAME, datasets)
    cxn.disconnect()




def recalibrate(boardname, carrierMin, carrierMax, zeroCarrierStep=0.025,
                sidebandCarrierStep=0.05, sidebandMax=0.35,
                sidebandStep=0.05, corrector=None):
    startReactor()
    block(recalibrateAsync, boardname, carrierMin, carrierMax,
          zeroCarrierStep, sidebandCarrierStep, sidebandMax,
                sidebandStep, corrector)
