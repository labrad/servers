# Copyright (C) 2007  Max Hofheinz 
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
import labrad

SETUPTYPESTRINGS = ['no IQ mixer', \
                    'DAC A -> mixer I, DAC B -> mixer Q',\
                    'DAC A -> mixer Q, DAC B -> mixer I']
SESSIONNAME = 'GHzDAC Calibration'
ZERONAME = 'zero'
PULSENAME = 'pulse'
IQNAME = 'IQ'


def getDataSet(dslist, fpganame, caltype, errorClass=None):
    index=len(dslist) - 1
    while (index >=0) and (not dslist[index][8:] == fpganame + ' - ' + caltype):
        index-=1
    if index < 0:
        if errorClass:
            raise errorClass(fpganame, caltype)
        else: 
            print 'Warning: No %s calibration found for %s.' % \
                  (caltype, fpganame)
            print '         No %s correction will be performed.' % (caltype)
            return None
    else:
        print 'Loading %s calibration from %s...' % (caltype, dslist[index])
        return dslist[index]



def IQcorrector(fpganame, connection = None, 
                zerocor = True, pulsecor = True, iqcor = True,
                lowpass = cosinefilter, bandwidth = 0.4):

    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.cionnect argument
    """
    cxn=connection or labrad.connect()
    ds=cxn.data_server
    ctx = ds.context()
    ds.open_session(SESSIONNAME,context=ctx)
    dslist=ds.list_datasets(context=ctx)

    corrector = IQcorrection(lowpass, bandwidth)

    # Load Zero Calibration
    if zerocor:
        dataset = getDataSet(dslist, fpganame, ZERONAME)
        if dataset:
            ds.open_dataset(dataset, context=ctx)
            corrector.loadZeroCal(ds.get_all_datapoints(context=ctx))
    

    #Load pulse response
    if pulsecor:
        dataset = getDataSet(dslist, fpganame, PULSENAME)
        if dataset:
            ds.open_dataset(dataset, context=ctx)
            setupType = int(round(\
                ds.get_parameter('Setup type',context=ctx)))
            print '  %s' % SETUPTYPESTRINGS[setupType]
            IisB = (setupType == 2)
            carrierfreq=ds.get_parameter('Anritsu frequency [GHz]',
                                         context=ctx)
            corrector.loadPulseCal(ds.get_all_datapoints(context=ctx),
                                   carrierfreq, IisB)
            
    # Load Sideband Calibration
    if iqcor:
        dataset = getDataSet(dslist, fpganame, IQNAME)
        if dataset:
            ds.open_dataset(dataset, context=ctx)
            sidebandStep = ds.get_parameter('Sideband frequency step [GHz]',
                                        context=ctx)
            sidebandCount = \
                int(round(ds.get_parameter('Number of sideband frequencies',
                                           context=ctx)))
            datapoints = ds.get_all_datapoints(context=ctx)
            corrector.loadSidebandCal(datapoints, sidebandCount, sidebandStep)
 
    if not connection:
        cxn.disconnect()
            
    return corrector    


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
        cxn = yield labrad.connect()
        
    ds=cxn.data_server
    ctx = ds.context()

    yield ds.open_session(SESSIONNAME,context=ctx)
    dslist = yield ds.list_datasets(context=ctx)

    corrector = IQcorrection(lowpass, bandwidth)

    # Load Zero Calibration
    if zerocor:
        dataset = getDataSet(dslist, fpganame, ZERONAME, errorClass)
        if dataset:
            yield ds.open_dataset(dataset,context=ctx)
            datapoints = yield ds.get_all_datapoints(context=ctx)
            corrector.loadZeroCal(datapoints)
    

    #Load pulse response
    if pulsecor:
        dataset = getDataSet(dslist, fpganame, PULSENAME, errorClass)
        if dataset:
            yield ds.open_dataset(dataset,context=ctx)
            setupType = int(round(\
                        (yield ds.get_parameter('Setup type',context=ctx))))
            print '  %s' % SETUPTYPESTRINGS[setupType]
            IisB = (setupType == 2)
            datapoints = yield ds.get_all_datapoints(context=ctx)
            carrierfreq = yield ds.get_parameter('Anritsu frequency [GHz]',
                                                 context=ctx)
            corrector.loadPulseCal(datapoints, carrierfreq, IisB)
 

    # Load Sideband Calibration
    if iqcor:
        dataset = getDataSet(dslist, fpganame, IQNAME, errorClass)
        if dataset:
            yield ds.open_dataset(dataset,context=ctx)
            sidebandStep = \
                yield ds.get_parameter('Sideband frequency step [GHz]',
                                              context=ctx)
            sidebandCount = int(round(\
                (yield ds.get_parameter('Number of sideband frequencies',
                                        context=ctx))))
            datapoints = yield ds.get_all_datapoints(context=ctx)
            corrector.loadSidebandCal(datapoints,sidebandCount,sidebandStep)

    if not connection:
        yield cxn.disconnect()

    returnValue(corrector)


def DACcorrector(fpganame, channel, connection = None, \
                 lowpass = gaussfilter, bandwidth = 0.13):

    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.connect argument
    """
    cxn=connection or labrad.connect()
    ds=cxn.data_server()
    ctx = ds.context()

    ds.open_session(SESSIONNAME,context=ctx)
    dslist=ds.list_datasets(context=ctx)

    corrector = DACcorrection(lowpass, bandwidth)

    dataset= getDataSet(dslist, fpganame, PULSENAME)
    if dataset:
        ds.open_dataset(dataset, context=ctx)
        setupType = int(round(\
            ds.get_parameter('Setup type',context=ctx)))
        if setupType != 0:
            print '    Calset is for board with IQ mixer. Not loading'
        else:
            datapoints=ds.get_all_datapoints(context=ctx)
            corrector.loadCal(datapoints, channel)

    if not connection:
        cxn.disconnect()

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
        cxn = yield labrad.connect()

    ds=cxn.data_server
    ctx = ds.context()

    yield ds.open_session(SESSIONNAME,context=ctx)
    dslist = yield ds.list_datasets(context=ctx)

    corrector = DACcorrection(lowpass, bandwidth)

    dataset = getDataSet(dslist, fpganame, PULSENAME, errorClass)
    if dataset:
        yield ds.open_dataset(dataset, context=ctx)
        setupType = int(round((yield ds.get_parameter('Setup type',context=ctx))))
        if setupType != 0:
            if errorClass:
                raise errorClass(fpganame, PULSENAME)
            else:
                print '    Calset is for board with IQ mixer. Not loading'
        else:
            datapoints = yield ds.get_all_datapoints(context=ctx)
            corrector.loadCal(datapoints, channel)
        print '  Done.'
    if not connection:
        yield cxn.disconnect()
        
    returnValue(corrector)
