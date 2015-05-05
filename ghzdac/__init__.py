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

#
# Version 1.1.0
#
# History
#
# 1.1.0   2008/06/17  added recalibrations and possibility to load several
# calibration files
# 1.0.0               first stable version


from __future__ import with_statement

from numpy import shape, array, size
import numpy as np

import labrad

from correction import (DACcorrection, IQcorrection,
                        cosinefilter, gaussfilter, flatfilter)
import keys
import calibrate
import logging


def aequal(a, b):
    return (shape(a) == shape(b)) and (all(a == b))


def getDataSets(cxn, boardname, caltype, errorClass=None):
    reg = cxn.registry
    ds = cxn.data_vault
    reg.cd(['', keys.SESSIONNAME, boardname], True)
    if caltype in (reg.dir())[1]:
        calfiles = (reg.get(caltype))
    else:
        calfiles = array([])

    if not size(calfiles):
        if isinstance(errorClass, Exception):
            raise errorClass(caltype)
        elif errorClass != 'quiet':
            print 'Warning: No %s calibration loaded.' % caltype
            print '         No %s correction will be performed.' % caltype

    return (calfiles)


def IQcorrector(fpganame, connection,
                     zerocor=True, pulsecor=True, iqcor=True,
                     lowpass=cosinefilter, bandwidth=0.4, errorClass='quiet'):
    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.connect argument
    """

    if connection:
        cxn = connection
        logging.debug("using received cxn: {}".format(cxn))
    else:
        cxn = labrad.connect()

    ds = cxn.data_vault
    ds.cd(['', keys.SESSIONNAME, fpganame], True)
    corrector = IQcorrection(fpganame, lowpass, bandwidth)
    # Load Zero Calibration
    if zerocor:
        datasets = getDataSets(cxn, fpganame, keys.ZERONAME, errorClass)
        logging.debug('datasets: {}'.format(datasets))
        for dataset in datasets:
            filename = ds.open(long(dataset))
            logging.debug('Loading zero calibration from: {}'.format(filename[1]))
            datapoints = ds.get()
            datapoints = np.array(datapoints)
            corrector.loadZeroCal(datapoints, dataset)
    # Load pulse response
    if pulsecor:
        dataset = getDataSets(cxn, fpganame, keys.PULSENAME, errorClass)
        if dataset != []:
            dataset = dataset[0]
            filename = ds.open(long(dataset))
            logging.debug('Loading pulse calibration from: {}'.format(filename[1]))
            setupType = ds.get_parameter(keys.IQWIRING)
            logging.info('setupType: {}'.format(setupType))
            IisB = (setupType == keys.SETUPTYPES[2])
            datapoints = ds.get()
            datapoints = np.array(datapoints)
            carrierfreq = (ds.get_parameter(keys.PULSECARRIERFREQ))['GHz']
            corrector.loadPulseCal(datapoints, carrierfreq, dataset, IisB)
    # Load Sideband Calibration
    if iqcor:
        datasets = getDataSets(cxn, fpganame, keys.IQNAME, errorClass)
        for dataset in datasets:
            filename = ds.open(long(dataset))
            logging.debug('Loading sideband calibration from: {}'.format(filename[1]))
            sidebandStep = \
                (ds.get_parameter('Sideband frequency step'))['GHz']
            sidebandCount = \
                ds.get_parameter('Number of sideband frequencies')
            datapoints = ds.get()
            datapoints = np.array(datapoints)
            corrector.loadSidebandCal(datapoints, sidebandStep, dataset)
    if not connection:
        cxn.disconnect()
    return corrector


def DACcorrector(fpganame, channel, connection=None,
                      lowpass=gaussfilter, bandwidth=0.13, errorClass='quiet', maxfreqZ=0.45):
    """
    Returns a DACcorrection object for the given DAC board.
    The argument has the same form as the
    dms.python_fpga_server.connect argument
    """
    if connection:
        cxn = connection
    else:
        cxn = labrad.connect()

    ds = cxn.data_vault

    ds.cd(['', keys.SESSIONNAME, fpganame], True)

    corrector = DACcorrection(fpganame, channel, lowpass, bandwidth)

    if not isinstance(channel, str):
        channel = keys.CHANNELNAMES[channel]

    dataset = getDataSets(cxn, fpganame, channel, errorClass)
    if dataset != []:
        logging.debug("Dataset - fpganame: {} channel: {}".format(fpganame, channel))
        dataset = dataset[0]
        logging.debug("Loading pulse calibration from: {}".format(dataset))
        ds.open(dataset)
        datapoints = ds.get()
        datapoints = np.array(datapoints)
        corrector.loadCal(datapoints, maxfreqZ=maxfreqZ)
    if not connection:
        cxn.disconnect()

    return corrector


def recalibrate(boardname, carrierMin, carrierMax, zeroCarrierStep=0.025,
                     sidebandCarrierStep=0.05, sidebandMax=0.35, sidebandStep=0.05,
                     corrector=None):
    cxn = labrad.connect()
    ds = cxn.data_vault
    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, boardname])
    anritsuID = reg.get(keys.ANRITSUID)
    anritsuPower = (reg.get(keys.ANRITSUPOWER))['dBm']
    if corrector is None:
        corrector = IQcorrector(boardname, cxn)
    if corrector.board != boardname:
        logging.info('Provided corrector is not for: {}'.format(boardname))
        logging.info('Loading new corrector. Provided corrector will not be updated.')
        corrector = IQcorrector(boardname, cxn)

    if zeroCarrierStep is not None:
        # check if a corrector has been provided and if it is up to date
        # or if we have to load a new one.
        if not aequal(corrector.zeroCalFiles,
                      (getDataSets(cxn, boardname, keys.ZERONAME, 'quiet'))):
            logging.info('Provided corrector is outdated.')
            logging.info('Loading new corrector. Provided corrector will not be updated.')
            corrector = IQcorrector(boardname, cxn)

        # do the zero calibration
        dataset = calibrate.zeroScanCarrier(cxn,
                                                  {'carrierMin': carrierMin,
                                                   'carrierMax': carrierMax,
                                                   'carrierStep': zeroCarrierStep},
                                                  boardname)
        # load it into the corrector
        ds.open(dataset)
        datapoints = (ds.get()).asarray
        corrector.loadZeroCal(datapoints, dataset)
        # eliminate obsolete zero calibrations
        datasets = corrector.eliminateZeroCals()
        # and save which ones are being used now
        reg.cd(['', keys.SESSIONNAME, boardname], True)
        reg.set(keys.ZERONAME, datasets)
    if sidebandCarrierStep is not None:
        # check if a corrector has been provided and if it is up to date
        # or if we have to load a new one.
        if not (aequal(corrector.sidebandCalFiles,
                       (getDataSets(cxn, boardname, keys.IQNAME, 'quiet'))) and \
                        aequal(array([corrector.pulseCalFile]),
                               (getDataSets(cxn, boardname, keys.PULSENAME, 'quiet')))):
            logging.info('Provided correcetor is outdated.')
            logging.info('Loading new corrector. Provided corrector will not be updated.')
            corrector = IQcorrector(boardname, cxn)

        # do the pulse calibration
        dataset = calibrate.sidebandScanCarrier(cxn,
                                                      {'carrierMin': carrierMin,
                                                       'carrierMax': carrierMax,
                                                       'sidebandCarrierStep': sidebandCarrierStep,
                                                       'sidebandFreqStep': sidebandStep,
                                                       'sidebandFreqCount': int(sidebandMax / sidebandStep + 0.5) * 2},
                                                      boardname, corrector)
        # load it into the corrector
        ds.open(dataset)
        sidebandStep = \
            (ds.get_parameter('Sideband frequency step'))['GHz']
        sidebandCount = \
            ds.get_parameter('Number of sideband frequencies')
        datapoints = (ds.get()).asarray
        corrector.loadSidebandCal(datapoints, sidebandStep, dataset)
        # eliminate obsolete zero calibrations
        datasets = corrector.eliminateSidebandCals()
        # and save which ones are being used now
        reg.cd(['', keys.SESSIONNAME, boardname], True)
        reg.set(keys.IQNAME, datasets)
    cxn.disconnect()
    return corrector


def runsequence(sram, cor):
    with labrad.connection() as cxn:
        fpga = cxn.ghz_dacs
        fpga.select_device(cor.board)
        if hasattr(cor, 'channel') and cor.channel == 1:
            sram = sram << 14
        sram[0:4] |= 0xF << 28
        fpga.run_sram(sram, True)
        
        
    

