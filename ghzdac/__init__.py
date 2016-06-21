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
                        cosine_filter, gaussfilter, flatfilter)
import keys
import calibrate
import logging


def a_equal(a, b):
    """
    Test if two arrays have same shape and have equal elements.
    Args:
        a (np.ndarray): array
        b (np.ndarray): array

    Returns (bool):
    """
    return (shape(a) == shape(b)) and (all(a == b))


def get_data_sets(cxn, board_name, cal_type, error_class=None):

    """
    Grabs a calibration file from pointers in the GHzDAC Calibration registry.
    Args:
        cxn (labrad.client.Client): labrad connection object.
        board_name (str): Name of board as listed in FPGA Server
                (format 'board_group DAC/ADC board_number',
                i.e. 'DR Lab DAC 12').
        cal_type (str): Type of calibration to look for (list includes
            'pulse', 'zero', and 'IQ')
        error_class (None, 'quiet', or Exception): If Exception, raises this
            when the cal_file is length zero.  If 'quiet' raises no exception.
            If None, raises a pre-written exception.

    Returns (np.ndarray):
        Datavault number in an array size = (1,) or empty array.
    """

    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, board_name], True)
    if cal_type in (reg.dir())[1]:
        cal_files = (reg.get(cal_type))
    else:
        cal_files = array([])

    if not size(cal_files):
        if isinstance(error_class, Exception):
            raise error_class(cal_type)
        elif error_class != 'quiet':
            print 'Warning: No {} calibration loaded.'.format(cal_type)
            print '         {} not corrected.'.format(cal_type)

    return cal_files


def iq_corrector(fpga_name, connection,
                 zero_correction=True, pulse_correction=True,
                 iq_correction=True, low_pass=cosine_filter, bandwidth=0.4,
                 error_class='quiet'):
    """
        Perform corrections on a given board.

        The argument has the same form as dms.python_fpga_server.connect
    Args:
        fpga_name (str): Name of board as listed in FPGA Server
                (format 'board_group DAC/ADC board_number',
                i.e. 'DR Lab DAC 12').
        connection (bool or labrad.client.Client): Labrad connection object if
            currently running, creates temporary connection if false.
        zero_correction (bool): Perform a zeroing correction.
        pulse_correction (bool): Perform the pulse correction.
        iq_correction (bool): Perform the IQ correction.
        low_pass (func): Transfer function desired after IQ correction
        bandwidth (float): If low pass is not specified, the transfer function
            will be flat and then roll off between (1-bandwidth)*Nyquist and
            Nyquist.
        error_class (None, 'quiet', or Exception): If Exception, raises this
            when the cal_file is length zero.  If 'quiet' raises no exception.
            If None, raises a pre-written exception.

    Returns (correction.IQcorrection):
        DACcorrection object for the given DAC board.
    """

    if connection:
        cxn = connection
        logging.debug("using received cxn: {}".format(cxn))
    else:
        cxn = labrad.connect()

    ds = cxn.data_vault
    ds.cd(['', keys.SESSIONNAME, fpga_name], True)
    corrector = IQcorrection(fpga_name, low_pass, bandwidth)
    # Load Zero Calibration
    if zero_correction:
        data_sets = get_data_sets(cxn, fpga_name, keys.ZERONAME, error_class)
        logging.debug('datasets: {}'.format(data_sets))
        for data_set in data_sets:
            filename = ds.open(long(data_set))
            logging.debug('Loading zero calibration from: {}'.
                          format(filename[1]))
            data_points = ds.get()
            data_points = np.array(data_points)
            corrector.loadZeroCal(data_points, data_set)
    # Load pulse response
    if pulse_correction:
        data_set = get_data_sets(cxn, fpga_name, keys.PULSENAME, error_class)
        if data_set != []:
            data_set = data_set[0]
            filename = ds.open(long(data_set))
            logging.debug('Loading pulse calibration from: {}'.
                          format(filename[1]))
            setupType = ds.get_parameter(keys.IQWIRING)
            logging.info('setupType: {}'.format(setupType))
            IisB = (setupType == keys.SETUPTYPES[2])
            data_points = ds.get()
            data_points = np.array(data_points)
            carrierfreq = (ds.get_parameter(keys.PULSECARRIERFREQ))['GHz']
            corrector.loadPulseCal(data_points, carrierfreq, data_set, IisB)
    # Load Sideband Calibration
    if iq_correction:
        data_sets = get_data_sets(cxn, fpga_name, keys.IQNAME, error_class)
        for data_set in data_sets:
            filename = ds.open(long(data_set))
            logging.debug('Loading sideband calibration from: {}'.
                          format(filename[1]))
            sidebandStep = (
                ds.get_parameter('Sideband frequency step'))['GHz']
            data_points = ds.get()
            data_points = np.array(data_points)
            corrector.loadSidebandCal(data_points, sidebandStep, data_set)
    if not connection:
        cxn.disconnect()

    return corrector


def DAC_corrector(fpga_name, channel, connection=False,
                  low_pass=gaussfilter, bandwidth=0.13, error_class='quiet',
                  max_frequency_z=0.45):
    """
    Perform corrections on a given board.

    The argument has the same form as dms.python_fpga_server.connect

    Args:
        fpga_name (str): Name of board as listed in FPGA Server
                (format 'board_group DAC/ADC board_number',
                i.e. 'DR Lab DAC 12').
        channel (str): 'DAC A' or ''DAC B' if this is a two port 'DC' board.
        connection (bool or labrad.client.Client): Labrad connection object if
            currently running, creates temporary connection if false.
        low_pass (func): Transfer function desired after IQ correction
        bandwidth (float): If low pass is not specified, the transfer function
            will be flat and then roll off between (1-bandwidth)*Nyquist and
            Nyquist.
        error_class (None, 'quiet', or Exception): If Exception, raises this
            when the cal_file is length zero.  If 'quiet' raises no exception.
            If None, raises a pre-written exception.
        max_frequency_z (float):
    Returns (correction.IQcorrection):
        DACcorrection object for the given DAC board.
    """

    if connection:
        cxn = connection
    else:
        cxn = labrad.connect()

    ds = cxn.data_vault
    ds.cd(['', keys.SESSIONNAME, fpga_name], True)
    corrector = DACcorrection(fpga_name, channel, low_pass, bandwidth)

    if not isinstance(channel, str):
        channel = keys.CHANNELNAMES[channel]

    data_set = get_data_sets(cxn, fpga_name, channel, error_class)
    if not np.empty(data_set):
        logging.debug("Data_set - fpga_name: {} channel: {}".
                      format(fpga_name, channel))
        data_set = data_set[0]
        logging.debug("Loading pulse calibration from: {}".
                      format(data_set))
        ds.open(data_set)
        data_points = ds.get()
        data_points = np.array(data_points)
        corrector.loadCal(data_points, maxfreqZ=max_frequency_z)

    if not connection:
        cxn.disconnect()

    return corrector


def recalibrate(board_name, carrier_min_ghz, carrier_max_ghz,
                zero_carrier_step_ghz=0.025, sideband_carrier_step_ghz=0.05,
                sideband_max_ghz=0.35, sideband_step_ghz=0.05, corrector=None):
    """
    Perform corrections on a given board.

    I don't know what this does or if it is used anywhere.

    The argument has the same form as dms.python_fpga_server.connect

    Args:
        board_name (str): Name of board as listed in FPGA Server
                (format 'board_group DAC/ADC board_number',
                i.e. 'DR Lab DAC 12').
        carrier_min_ghz (float): Minimum frequency of carrier zeroing
            calibration (in GHz).
        carrier_max_ghz (float): Maximum frequency of carrier zeroing
            calibration (in GHz).
            currently running, creates temporary connection if false.
        zero_carrier_step_ghz (float): Step to iterate over while zeroing
            carrier (in GHz).
        sideband_carrier_step_ghz (float):
        sideband_max_ghz (float):
        sideband_step_ghz (float):
        corrector (None or ):

    Returns (correction.IQcorrection):
        DACcorrection object for the given DAC board.
    """

    cxn = labrad.connect()
    ds = cxn.data_vault
    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, board_name])

    if corrector is None:
        corrector = iq_corrector(board_name, cxn)
    if corrector.board != board_name:
        logging.info('Provided corrector is not for: {}'.format(board_name))
        logging.info('Loading new corrector. ' +
                     'Provided corrector will not be updated.')
        corrector = iq_corrector(board_name, cxn)

    if zero_carrier_step_ghz is not None:
        # check if a corrector has been provided and if it is up to date
        # or if we have to load a new one.
        if not a_equal(corrector.zeroCalFiles,
                       (get_data_sets(cxn, board_name, keys.ZERONAME,
                                      'quiet'))):
            logging.info('Provided corrector is outdated.')
            logging.info('Loading new corrector. ' +
                         'Provided corrector will not be updated.')
            corrector = iq_corrector(board_name, cxn)

        # do the zero calibration
        data_set = calibrate.zeroScanCarrier(cxn,
                                             {'carrierMin': carrier_min_ghz,
                                              'carrierMax': carrier_max_ghz,
                                              'carrierStep': zero_carrier_step_ghz},
                                             board_name)
        # load it into the corrector
        ds.open(data_set)
        data_points = (ds.get()).asarray
        corrector.loadZeroCal(data_points, data_set)
        # eliminate obsolete zero calibrations
        data_sets = corrector.eliminateZeroCals()
        # and save which ones are being used now
        reg.cd(['', keys.SESSIONNAME, board_name], True)
        reg.set(keys.ZERONAME, data_sets)

    if sideband_carrier_step_ghz is not None:
        # check if a corrector has been provided and if it is up to date
        # or if we have to load a new one.
        check_1 = (a_equal(corrector.sidebandCalFiles,
                           (get_data_sets(cxn, board_name, keys.IQNAME,
                                          'quiet'))))
        check_2 = (a_equal(array([corrector.pulseCalFile]),
                           (get_data_sets(cxn, board_name, keys.PULSENAME,
                                          'quiet'))))
        if not check_1 and check_2:
            logging.info('Provided corrector is outdated.')
            logging.info('Loading new corrector. ' +
                         'Provided corrector will not be updated.')
            corrector = iq_corrector(board_name, cxn)

        # do the pulse calibration
        num_points = int(sideband_max_ghz / sideband_step_ghz + 0.5) * 2
        data_dict = {'carrierMin': carrier_min_ghz,
                     'carrierMax': carrier_max_ghz,
                     'sidebandCarrierStep': sideband_carrier_step_ghz,
                     'sidebandFreqStep': sideband_step_ghz,
                     'sidebandFreqCount': num_points}

        data_set = calibrate.sidebandScanCarrier(cxn, data_dict, board_name,
                                                 corrector)
        # load it into the corrector
        ds.open(data_set)
        sideband_step_ghz = (ds.get_parameter('Sideband frequency step'))['GHz']
        data_points = (ds.get()).asarray
        corrector.loadSidebandCal(data_points, sideband_step_ghz, data_set)
        # eliminate obsolete zero calibrations
        data_sets = corrector.eliminateSidebandCals()
        # and save which ones are being used now
        reg.cd(['', keys.SESSIONNAME, board_name], True)
        reg.set(keys.IQNAME, data_sets)

    cxn.disconnect()

    return corrector


def run_sequence(s_ram, correction):

    """
    I don't know what this does or if it is used anywhere.
    Args:
        s_ram:
        correction:

    Returns:
    """

    with labrad.connection() as cxn:
        fpga = cxn.ghz_dacs
        fpga.select_device(correction.board)

        if hasattr(correction, 'channel') and correction.channel == 1:
            s_ram = s_ram << 14

        s_ram[0:4] |= 0xF << 28
        fpga.run_sram(s_ram, True)

