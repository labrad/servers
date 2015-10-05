"""This module runs the board calibrations.

Quick start::

.. code:: python

    import ghzdac_cal.GHz_DAC_calibrate as gc
    gc.calibrate_iq(cxn, ['Vince DAC 11'])
    # or if you want to do all the boards in one go:
    gc.calibrate_iq(cxn, gc.find_microwave_dacs(cxn))

Generally, this module calls calibration code in the ``ghzdac`` package.
Therefore, this module requires that the ``servers`` repository is in the Python
path (the ``servers/`` directory should be put on the Python path, not its
parent directory. When this is set up properly, ``import ghzdac`` will succeed.

The most user-facing functions in this module are at the bottom; recommended
reading order is bottom-to-top (i.e. start with ``calibrate_iq``, then
``find_microwave_dacs``, and so on.

"""
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

# This is the user interface to the calibration scripts for a initial
# calibration

# HOW TO USE
#
# 1 calibrate_pulse. This calibrates the microwave envelope shape.
# 2 calibrate_iq. This calibrates the I and Q dc levels needed to zero the rf
#   output, and also calibrates the I and Q amplitudes needed to null the
#   unwanted sideband.

from __future__ import with_statement, absolute_import

from numpy import clip

import labrad
import labrad.async

# GHz_DAC_calibrate is only a front-end, the actual calibration
# routines are in ghzdac.calibrate

import ghzdac
import ghzdac.calibrate as calibrate
import ghzdac.keys as keys

FPGA_SERVER_NAME = 'ghz_fpgas'

def calibrate_dc_pulse(fpga_name, channel, dc_scope):
    """ Calls ghzdac.calibrate.calibrateDCPulse, synchronously.

    :param str fpga_name: e.g. "Vince DAC 11"
    :param int channel: 0 for A, 1 for B
    :param str dc_scope: 'sampling_scope' or 'infiniium'
    :return int: dataset number
    """
    with labrad.connect() as cxn:
        if dc_scope == 'sampling_scope':
            return calibrate.calibrateDCPulse(cxn, fpga_name, channel)
        elif dc_scope == 'infiniium':
            return calibrate.calibrateDCPulse_infiniium(cxn, fpga_name, channel, 'EXT')
        else:
            raise Exception("invalid scope: {}".format(dc_scope))


def zero_fixed_carrier(fpga_name, use_switch=True):
    """ Calls ghzdac.calibrate.zeroFixedCarrier, synchronously.
    :param str fpga_name: e.g. "Vince DAC 11"
    :param bool use_switch: Whether to use microwave switch
    :return list[int]: zeros for A and B
    """
    with labrad.connect() as cxn:
        return calibrate.zeroFixedCarrier(cxn, fpga_name, use_switch=use_switch)


def calibrate_ac_pulse(fpga_name, zero_a, zero_b, use_switch=True):
    """ Calls ghzdac.calibrate.calibrateACPulse, synchronously.

    :param str fpga_name:
    :param int zero_a: Zero for channel A, in DAC units (i.e. 0 < x < 0x1FFF)
    :param int zero_b: channel B
    :param bool use_switch: Whether to use microwave switch
    :return int: dataset number
    """
    with labrad.connect() as cxn:
        return calibrate.calibrateACPulse(cxn, fpga_name, zero_a, zero_b,
                                          use_switch=use_switch)


def calibrate_pulse(cxn, fpga_name, dc_scope = 'infiniium'):
    """
    :param labrad connection object cxn:
    :param str fpga_name: corresponds with registry, e.g. "Vince DAC 11"
    :param str dc_scope: 'sampling_scope' or 'infiniium'
    :return:
    """

    if not isinstance(fpga_name, str):
        node_name = cxn[FPGA_SERVER_NAME].list_dacs()[0].partition(' DAC')[0]  # pull out node name by looking at dacs
        fpga_name = node_name + ' DAC ' + str(fpga_name)

    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, fpga_name], True)
    wiring = reg.get(keys.IQWIRING)
    print "Board: %s, wiring: %s" % (fpga_name, wiring)
    board_type = None
    if wiring in keys.SETUPTYPES[1:3]:
        board_type = 'ac'
    elif wiring == keys.SETUPTYPES[0]:
        board_type = 'dc'
    
    if board_type == 'ac':
        use_switch = reg.get(keys.SWITCHUSE, 'b', True, True)
        zero_a, zero_b = zero_fixed_carrier(fpga_name, use_switch=use_switch)
        dataset = calibrate_ac_pulse(fpga_name, zero_a, zero_b,
                                     use_switch=use_switch)
        reg.set(keys.PULSENAME, [dataset])
    elif board_type == 'dc':
        channel = int(raw_input('Select channel: 0 (DAC A) or 1 (DAC B): '))
        dataset = calibrate_dc_pulse(fpga_name, channel, dc_scope=dc_scope)
        reg.set(keys.CHANNELNAMES[channel], [dataset])


def zero_scan_carrier(fpga_name, scan_params, use_switch=True):
    """ Calls ghzdac.calibrate.zeroScanCarrier, synchronously.

    :param str fpga_name: corresponds with registry, e.g. "Vince DAC 11"
    :param dict scan_params: parameters dictionary
    :return int: dataset number
    """
    with labrad.connect() as cxn:
        return calibrate.zeroScanCarrier(cxn, scan_params, fpga_name, use_switch=use_switch)


def iq_corrector(fpga_name):
    """ Calls ghzdac.IQcorrectorAsync, synchronously.

    :param str fpga_name: e.g. "Vince DAC 11"
    :return ghzdac.correction.IQcorrection: IQ correction object
    """
    with labrad.connect() as cxn:
        return ghzdac.IQcorrector(fpga_name, cxn, pulsecor=False)


def sideband_scan_carrier(fpga_name, scan_params, corrector, use_switch=True):
    """ Calls ghzdac.calibrate.sidebandScanCarrier, synchronously.

    :param fpga_name: e.g. "Vince DAC 11"
    :param dict scan_params: parameters dict
    :param ghzdac.correction.IQcorrection corrector: corrector object, from e.g. iq_corrector
    :return:
    """
    with labrad.connect() as cxn:
        corrector.dynamicReserve = 4.0  # TODO: I don't know why we do this.
        return calibrate.sidebandScanCarrier(cxn, scan_params, fpga_name, corrector, use_switch=use_switch)


def modify_scan_params(carrier_start, carrier_stop, carrier_step, sideband_carrier_step, sideband_step, sideband_count):
    """
    Generates a dictionary used to determine frequencies for calibration

    :param labrad.Value carrier_start: e.g. 4 GHz
    :param labrad.Value carrier_stop: e.g. 7 GHz
    :param labrad.Value carrier_step: e.g. 0.05 GHz
    :param labrad.Value sideband_carrier_step: e.g. 0.05 GHz
    :param labrad.Value sideband_step: e.g. 0.05 GHz
    :param labrad.Value sideband_count: e.g. 14
    :return dict scan_params: dict with frequency parameters for calibration
    """

    scan_params = {}

    maxsidebandfreq = clip(0.5 * (sideband_count - 1.0) * sideband_step['GHz'], 1e-3, 0.5)

    scan_params['carrierMin'] = clip(carrier_start['GHz'], 0, 20)
    scan_params['carrierMax'] = clip(carrier_stop['GHz'], 0, 20)
    scan_params['carrierStep'] = carrier_step['GHz']
    scan_params['sidebandCarrierStep'] = sideband_carrier_step['GHz']
    scan_params['sidebandFreqStep'] = calibrate.validSBstep(sideband_step['GHz'])
    scan_params['sidebandFreqCount'] = int(maxsidebandfreq / scan_params['sidebandFreqStep'] + 0.5) * 2

    return scan_params


def find_microwave_dacs(cxn):
    """
    :param cxn: labrad connection object
    :return list microwave_dacs: list of microwave dacs (with IQ mixers)
    """

    microwave_dacs = []

    fpgas = cxn[FPGA_SERVER_NAME].list_devices()
    reg = cxn.registry

    for fpga in fpgas:
        if 'DAC' in fpga[1]:
            reg.cd(['', keys.SESSIONNAME, fpga[1]], True)
            wiring = reg.get(keys.IQWIRING)
            if wiring in keys.SETUPTYPES[1:3]:
                microwave_dacs.append(fpga[1])

    return microwave_dacs

# TODO: make a pause before starting a uwave switch=0 board


def calibrate_iq(cxn,
                 dacs_to_calibrate,
                 zero=True,
                 sideband=True,
                 carrier_start= 4*labrad.units.GHz,
                 carrier_stop=7*labrad.units.GHz,
                 carrier_step=0.025*labrad.units.GHz,
                 sideband_carrier_step=0.05*labrad.units.GHz,
                 sideband_step=0.05*labrad.units.GHz,
                 sideband_count=14,
                 use_switch=True):
    """Runs IQ mixer calibration for one or more DACs

    :param cxn: labrad connection object
    :param list[string] or list[int] or string dacs_to_calibrate: DAC or list of
        DACs to calibrate
    :param bool zero: whether to run the zero calibration
    :param bool sideband: whether to run the sideband calibration
    :param labrad.Value carrier_start: e.g. 4 GHz
    :param labrad.Value carrier_stop: e.g. 7 GHz
    :param labrad.Value carrier_step: e.g. 0.05 GHz
    :param labrad.Value sideband_carrier_step: e.g. 0.05 GHz
    :param labrad.Value sideband_step: e.g. 0.05 GHz
    :param labrad.Value sideband_count: e.g. 14
    """

    if dacs_to_calibrate == 'all':
        dacs_to_calibrate = find_microwave_dacs(cxn)
    elif not isinstance(dacs_to_calibrate, list):
        dacs_to_calibrate = [dacs_to_calibrate]
    num_strings = len([x for x in dacs_to_calibrate if isinstance(x, str)])
    if 0 < num_strings < len(dacs_to_calibrate):
        raise ValueError("Please pass in either all strings or no strings to dacs_to_calibrate.")
    if len([x for x in dacs_to_calibrate if isinstance(x, int)]) > 0:
        node_name = cxn[FPGA_SERVER_NAME].list_dacs()[0].partition(' DAC')[0]
        for idx in range(len(dacs_to_calibrate)):
            dac_number = dacs_to_calibrate[idx]
            dacs_to_calibrate[idx] = node_name + ' DAC ' + str(dac_number)

    scan_params = modify_scan_params(carrier_start, carrier_stop, carrier_step,
                                     sideband_carrier_step, sideband_step, sideband_count)

    # TODO: do we want to change how we get the registry keys? (i.e. away from ghzdac.keys)
    reg = cxn.registry
    for dac in dacs_to_calibrate:
        if zero:
            iq_dataset = zero_scan_carrier(dac, scan_params, use_switch=use_switch)
            reg.cd(['', keys.SESSIONNAME, dac], True)
            reg.set(keys.ZERONAME, [iq_dataset])
        if sideband:
            corrector = iq_corrector(dac)
            sideband_dataset = sideband_scan_carrier(dac, scan_params, corrector, use_switch=use_switch)
            reg.cd(['', keys.SESSIONNAME, dac], True)
            reg.set(keys.IQNAME, [sideband_dataset])
