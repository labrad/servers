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
from numpy import shape
SETUPTYPESTRINGS = ['no IQ mixer', \
                    'DAC A -> mixer I, DAC B -> mixer Q',\
                    'DAC A -> mixer Q, DAC B -> mixer I']
SESSIONNAME = 'GHzDAC Calibration'
ZERONAME = 'zero'
PULSENAME = 'pulse'
IQNAME = 'IQ'
CHANNELNAMES = ['DAC A','DAC B']


def getDataSet(dslist, caltype, errorClass=None):
    index=len(dslist) - 1
    while (index >=0) and (not dslist[index][8:] == caltype):
        index-=1
    if index < 0:
        if errorClass:
            raise errorClass(caltype)
        else: 
            print 'Warning: No %s calibration found.' % caltype
            print '         No %s correction will be performed.' % caltype
            return None
    else:
        print 'Loading %s calibration from %s.' % (caltype, dslist[index])
        return index+1



def IQcorrector(fpganame, connection = None, 
                zerocor = True, pulsecor = True, iqcor = True,
                lowpass = cosinefilter, bandwidth = 0.4):

    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.cionnect argument
    """
    cxn=connection or labrad.connect()
    ds=cxn.data_vault
    ctx = ds.context()
    ds.cd(['',SESSIONNAME,fpganame],context=ctx)
    dslist=ds.dir(context=ctx)[1]

    corrector = IQcorrection(lowpass, bandwidth)

    # Load Zero Calibration
    if zerocor:
        dataset = getDataSet(dslist, ZERONAME)
        if dataset:
            ds.open(dataset, context=ctx)
            corrector.loadZeroCal(ds.get(0xFFFFFFFF,True,context=ctx).asarray)
    

    #Load pulse response
    if pulsecor:
        dataset = getDataSet(dslist, PULSENAME)
        if dataset:
            ds.open(dataset, context=ctx)
            setupType = ds.get_parameter('Setup type',context=ctx)
            print '  %s' % setupType
            IisB = (setupType == SETUPTYPESTRINGS[2])
            carrierfreq = ds.get_parameter('Anritsu frequency',
                                           context=ctx)['GHz']
            corrector.loadPulseCal(ds.get(context=ctx), carrierfreq, IisB)
            
    # Load Sideband Calibration
    if iqcor:
        dataset = getDataSet(dslist, IQNAME)
        if dataset:
            ds.open(dataset, context=ctx)
            sidebandStep = ds.get_parameter('Sideband frequency step',
                                        context=ctx)['GHz']
            datapoints = ds.get(context=ctx).asarray
            corrector.loadSidebandCal(datapoints, sidebandStep)
 
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
        
    ds=cxn.data_vault
    ctx = ds.context()

    yield ds.cd(['',SESSIONNAME,fpganame],context=ctx)
    dslist = (yield ds.dir(context=ctx))[1]

    corrector = IQcorrection(lowpass, bandwidth)

    # Load Zero Calibration
    if zerocor:
        dataset = getDataSet(dslist, ZERONAME, errorClass)
        if dataset:
            yield ds.open(dataset,context=ctx)
            datapoints = (yield ds.get(context=ctx)).asarray
            corrector.loadZeroCal(datapoints)
    

    #Load pulse response
    if pulsecor:
        dataset = getDataSet(dslist, PULSENAME, errorClass)
        if dataset:
            yield ds.open(dataset,context=ctx)
            setupType = yield ds.get_parameter('Setup type',context=ctx)
            print '  %s' % setupType
            IisB = (setupType == SETUPTYPESTRINGS[2])
            datapoints = (yield ds.get(context=ctx)).asarray
            carrierfreq = (yield ds.get_parameter('Anritsu frequency',
                                                  context=ctx))['GHz']
            corrector.loadPulseCal(datapoints, carrierfreq, IisB)
 

    # Load Sideband Calibration
    if iqcor:
        dataset = getDataSet(dslist, IQNAME, errorClass)
        if dataset:
            yield ds.open(dataset,context=ctx)
            sidebandStep = \
                (yield ds.get_parameter('Sideband frequency step',
                                        context=ctx))['GHz']
            sidebandCount = \
                yield ds.get_parameter('Number of sideband frequencies',
                                        context=ctx)
            datapoints = (yield ds.get(context=ctx)).asarray
            corrector.loadSidebandCal(datapoints, sidebandStep)

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
    ds=cxn.data_vault
    ctx = ds.context()
    ds.cd(['',SESSIONNAME,fpganame],context=ctx)
    dslist=ds.dir(context=ctx)[1]

    corrector = DACcorrection(lowpass, bandwidth)

    if not isinstance(channel, str):
        channel = CHANNELNAMES[channel]

    dataset= getDataSet(dslist, channel)

    if dataset:
        ds.open(dataset, context=ctx)
        datapoints=ds.get(context=ctx).asarray
        corrector.loadCal(datapoints)

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

    ds=cxn.data_vault
    ctx = ds.context()

    yield ds.cd(['',SESSIONNAME,fpganame],context=ctx)
    dslist = (yield ds.dir(context=ctx))[1]

    corrector = DACcorrection(lowpass, bandwidth)

    if not isinstance(channel, str):
        channel = CHANNELNAMES[channel]

    dataset = getDataSet(dslist, channel, errorClass)
    if dataset:
        yield ds.open(dataset, context=ctx)
        datapoints = (yield ds.get(context=ctx)).asarray
        corrector.loadCal(datapoints)
    if not connection:
        yield cxn.disconnect()
        
    returnValue(corrector)
