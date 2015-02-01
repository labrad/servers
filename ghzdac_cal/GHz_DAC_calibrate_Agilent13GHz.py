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

from __future__ import with_statement

import os
from msvcrt import getch, kbhit

from numpy import  floor, clip
from twisted.internet.defer import inlineCallbacks, returnValue

import labrad
#from labrad.thread import blockingCallFromThread as block, startReactor
from labrad.thread import startReactor
from labrad.types import Value

#GHz_DAC_calibrate is only a front-end, the actual calibration
#routines are in ghzdac.calibrate
from servers.ghzdac.calibrate_Agilent13GHz import (zeroFixedCarrier, zeroScanCarrier, calibrateACPulse,
     calibrateDCPulse, sidebandScanCarrier, spectInit, validSBstep, SCOPECHANNEL,calibrateLinearity)
from servers.ghzdac import keys, IQcorrectorAsync
import time

FPGA_SERVER_NAME = 'ghz_fpgas'

HWDEFAULTS = {keys.ANRITSUPOWER: 2.7,
              keys.TIMEOFFSET: [2, 4, 4],
              keys.PULSECARRIERFREQ: 6.0,
              keys.SCOPESENSITIVITY: [100,2,2]}


#all frequencies in GHz
scanparams = {'carrier': 6.0,
              'carrierMin': 4.0,
              'carrierMax': 9.0,
              'carrierStep': 0.025,
              'sidebandCarrierStep': 0.05,
              'sidebandFreqStep': 0.05,
              'sidebandFreqCount': 14}

    
MINUTESFORPULSE = 5.0
MINUTESPERFREQUENCY = 0.17

def timeestimate(scanparams, count=1, zero=False, pulse=False, sideband=False):
    """Estimate the amount of time needed to perform various calibrations"""
    
    cMax, cMin, cStep = scanparams['carrierMax'], scanparams['carrierMin'], scanparams['carrierStep']
    scStep, sfCount = scanparams['sidebandCarrierStep'], scanparams['sidebandFreqCount']

    minutes = 0
    
    if zero:
        minutes += floor((cMax - cMin) / cStep + 1.001) * MINUTESPERFREQUENCY

    if pulse:
        minutes += MINUTESFORPULSE

    if pulse and (zero or sideband):
        #count some time for plugging cables
        minutes += 5.0

    if sideband:
        minutes += floor((cMax - cMin) / scStep + 1.001) * sfCount * MINUTESPERFREQUENCY

    minutes *= count
    if minutes < 30.5:
        minutes = int(round(minutes))
    else:
        minutes = int(round(minutes, -1))
    
    return '%dh%02d' % (minutes / 60, minutes % 60)
        

def clearscreen():
    os.system('cls')

def readfloat(message, default):
    message = '\n' + message + ' '
    try:
        return float(raw_input(message))
    except:
        return default

def waitforkey(message='Press key when done. ESC to abort'):
    print message
    while kbhit():
        getch()
    return getch() == '\x1b'

def selectitem(items, prompt, default=0, escape=True, returnIndex=True):
    "Present a basic menu"
    l = len(items)
    if l == 1:
        return items[0]

    if l == 0:
        if returnIndex:
            return -1
        else:
            return []            
    
    while kbhit():
        getch()
    if escape:
        prompt += ' (ESC to abort)'
    while True:
        clearscreen()
        print
        print prompt
        print
        for i, n in enumerate(items):
            if i == default:
                print '--> %s ' % n
            else:
                print '    %s' % n
        r = getch()
        if escape and r == '\x1b':
            return -1
        elif r == '\r':
            if returnIndex:
                return default
            else:
                return items[default]
        elif r == '\xe0':
            r = getch()
            if r == 'H':
                default -= 1
            elif r == 'P':
                default += 1
        default = default % l

def selectitems(items, prompt):
    l = len(items)
    if l == 1:
        return items
#        return items[0]

    if l == 0:
        if returnIndex:
            return -1
        else:
            return []            
    
    while kbhit():
        getch()
    default = 0
    selection = []
    while True:
        clearscreen()
        print
        print prompt + ' (SPACE to toggle, ESC to abort)'
        print
        for i, n in enumerate(items):
            if i == default:
                print '--> [%s] %s' % (' x'[i in selection], n)
            else:
                print '    [%s] %s' % (' x'[i in selection], n)
        r = getch()
        if r == '\x1b':
            return []
        elif r == '\r':
            selection.sort()
            return [items[i] for i in selection]
        elif r == ' ':
            if default in selection:
                selection.remove(default)
            else:
                selection.append(default)
        elif r == '\xe0':
            r = getch()
            if r == 'H':
                default -= 1
            elif r == 'P':
                default += 1
            default = default % l



@inlineCallbacks
def selectdevice(server, prompt, devicename, default=None, escape=True):
    device = yield server.list_devices()
    if not len(device):
        print 'No %s found. Cannot calibrate' % devicename
        while kbhit():
            getch()
        getch()
        exit()
    device = [d[1] for d in device]
    try:
        default = device.index(default)
    except:
        default = 0
    device = selectitem(device, prompt, returnIndex=False, escape=escape,
                        default=default)
    if device != -1:
        yield server.select_device(device)
    returnValue(device)




@inlineCallbacks
def modifyHWparamsSingle(cxn, boardname):
    fpga = cxn[FPGA_SERVER_NAME]
    reg = cxn.registry
    yield reg.cd(['', keys.SESSIONNAME, boardname], True)
    try:
        setup = yield reg.get(keys.IQWIRING)
        setup = keys.SETUPTYPES.index(setup)
    except:
        setup = 0
    clearscreen()
    print '\nDescribe the wiring of %s.' % boardname
    setup = selectitem(keys.SETUPTYPES, 'IQ mixer wiring of %s:' % boardname,
                       default=setup, escape=False)
    setupName = keys.SETUPTYPES[setup]
    ignoreExisting = not ((keys.IQWIRING in (yield reg.dir())[1]) and \
                     ((yield reg.get(keys.IQWIRING)) == setupName))
    if setup:
        anritsuID = yield selectdevice(cxn.anritsu_server,
                                       'Anritsu driving %s' % boardname,
                                       'Anritsu', escape=False)
        if keys.ANRITSUPOWER in (yield reg.dir())[1]:
            anritsuPower = (yield reg.get(keys.ANRITSUPOWER))['dBm']
        else:
            anritsuPower = HWDEFAULTS[keys.ANRITSUPOWER]
        anritsuPower = readfloat('Anritsu power: (%g dBm)' % anritsuPower,
                                 anritsuPower)
        if keys.PULSECARRIERFREQ in (yield reg.dir())[1]:
            pulseCarrierFreq = (yield reg.get(keys.PULSECARRIERFREQ))['GHz']
        else:
            pulseCarrierFreq = HWDEFAULTS[keys.PULSECARRIERFREQ]
        pulseCarrierFreq = readfloat('Carrier frequency for' +\
                                     ' pulse calibration: (%g GHz)' % \
                                     pulseCarrierFreq,
                                     pulseCarrierFreq)

        spectID = yield selectdevice(cxn.spectrum_analyzer_server,
                                     'Spectrum analyzer to use for calibrations',
                                     'spectrum analyzer', escape=False)
        keys.SWITCHPOSITION = 'Microwave switch position'
        if keys.SWITCHPOSITION in (yield reg.dir())[1]:
            switchPosition = (yield reg.get(keys.SWITCHPOSITION))
        else:
            switchPosition = 1
        switchPosition = int(round(readfloat('Microwave switch position for %s: (%d)' % \
                                             (boardname, switchPosition), switchPosition)))

    samplID = yield selectdevice(cxn.sampling_scope,
                                 'Sampling scope to use for calibrations',
                                 'sampling scope',escape=False)

    if not ignoreExisting and keys.TIMEOFFSET in (yield reg.dir())[1]:
        timeoffset = (yield reg.get(keys.TIMEOFFSET))['ns']
    else:
        timeoffset = HWDEFAULTS[keys.TIMEOFFSET][setup]
    timeoffset = readfloat('Delay of DAC outputs w/r to trigger ' + \
                           '(adjust such that the whole response is\n    visible and close to the beginning of the trace) (%g ns)' % \
                           timeoffset, timeoffset)
    if not ignoreExisting and keys.SCOPESENSITIVITY in (yield reg.dir())[1]:
        sens = (yield reg.get(keys.SCOPESENSITIVITY))['mV']
    else:
        sens = HWDEFAULTS[keys.SCOPESENSITIVITY][setup]
    sens = readfloat('Sampling scope sensitivity (%g mV/div)' % sens, sens)
    reg.set(keys.IQWIRING, setupName)
    if setup:
        yield reg.set(keys.ANRITSUID, anritsuID)
        yield reg.set(keys.ANRITSUPOWER, Value(anritsuPower, 'dBm'))
        yield reg.set(keys.PULSECARRIERFREQ, Value(pulseCarrierFreq, 'GHz'))
        yield reg.set(keys.SPECTID, spectID)
        yield reg.set(keys.SWITCHPOSITION, switchPosition)

    yield reg.set(keys.SCOPEID, samplID)
    yield reg.set(keys.SCOPESENSITIVITY, Value(sens, 'mV'))
    yield reg.set(keys.TIMEOFFSET, Value(timeoffset, 'ns'))
    
    

@inlineCallbacks
def modifyHWparams(cxn):
    fpga = cxn[FPGA_SERVER_NAME]
    reg = cxn.registry
    fpganame = None
    while True:
        fpganame = yield selectdevice(fpga,
                         'Select a GHzDAC board.',
                         'GHzDAC Board', default=fpganame)
        if fpganame == -1:
            return
        yield modifyHWparamsSingle(cxn, fpganame)

        

def modifyfrequencyrange(params):
    clearscreen()
    print ''
    maxsidebandfreq = 0.5 * (params['sidebandFreqCount'] - 1.0) \
                          * params['sidebandFreqStep']
    print 'Just hit enter to leave a value unchanged from the present value in parentheses'
    print 'Carrier frequency range for zero and sideband calibration:'

    params['carrierMin'] = float(clip(readfloat('   from (%.3g GHz): ' % params['carrierMin'], params['carrierMin']), 0.0, 40.0))
    params['carrierMax'] = float(clip(readfloat('   to (%.3g GHz): ' % params['carrierMax'], params['carrierMax']), params['carrierMin'], 40.0))
    params['carrierStep'] = float(clip(1e-3 * readfloat('Carrier frequency step for zero calibration (%.3g MHz): ' % (params['carrierStep'] * 1e3), params['carrierStep'] * 1e3), 1e-3, 1e3))
    params['sidebandCarrierStep'] = float(clip(1e-3 * readfloat('Carrier frequency step for sideband calibration (%.3g MHz): ' % (params['sidebandCarrierStep'] * 1e3), params['sidebandCarrierStep'] * 1e3), 1e-3, 1e3))
    params['sidebandFreqStep'] = validSBstep(1e-3 * readfloat('Sideband frequency step for sideband calibration (%.3g MHz): ' % (params['sidebandFreqStep'] * 1e3), params['sidebandFreqStep'] * 1e3))
    maxsidebandfreq = float(clip(1e-3 * readfloat('Maximum sideband frequency (%.3g MHz): ' % (maxsidebandfreq * 1e3), maxsidebandfreq * 1e3), 1e-3, 0.5))

    params['sidebandFreqCount'] = int(maxsidebandfreq / params['sidebandFreqStep'] + 0.5) * 2
    return params



    
    




@inlineCallbacks
def pulsecalibration(cxn):
    reg = cxn.registry
    fpga = cxn[FPGA_SERVER_NAME]
    fpganame = None
    while True:
        fpganame = yield selectdevice(fpga,
                         'Select a GHzDAC board to calibrate.',
                         'GHzDAC Board', default=fpganame)
        if fpganame == -1:
            return
        try: 
            yield reg.cd(['', keys.SESSIONNAME, fpganame], True)
            setup = yield reg.get(keys.IQWIRING)
        except:
            modifyHWparamsSingle(cxn, fpganame)
        clearscreen()
        if setup == keys.SETUPTYPES[0]:
            while True:
                choice = selectitem(['%s' % keys.CHANNELNAMES[0],
                                     '%s' % keys.CHANNELNAMES[1]],
                                    'Select a channel to calibrate on %s' \
                                    % fpganame)
                intorext10mhz = selectitem(['INT',
                                     'EXT'],
                                    'Select INT or EXT 10 MHz REF.')                                    
                if choice < 0:
                    break
                clearscreen()
                print
                print 'Measuring pulse response on %s' % fpganame
                print 
                print 'Connect:'
                print '    %s output           -->  SAMPLING SCOPE, channel %d' \
                      % (keys.CHANNELNAMES[choice], SCOPECHANNEL)

                print '    FPGA board S3+ output  -->  SAMPLING SCOPE, direct trigger input'
                print
                print 'Use the same cable length!'
                print

                if waitforkey():
                    break
                dataset = yield calibrateDCPulse(cxn, fpganame, choice,intorext10mhz)
                yield reg.set(keys.CHANNELNAMES[choice], [dataset])
        else:
            zeroA, zeroB = yield zeroFixedCarrier(cxn, fpganame)
            print ''
            print 'Measuring pulse responses on %s' % fpganame
            print 'Connect:'
            print '    IQ mixer chain output  -->  SAMPLING SCOPE, channel %d' \
                  % SCOPECHANNEL
            print '    FPGA board S3+ output  -->  SAMPLING SCOPE, direct trigger input'
            print 'Use the same cable length!'
            print ''
            if waitforkey():
                continue
            dataset = yield calibrateACPulse(cxn, fpganame, zeroA, zeroB)
            yield reg.set(keys.PULSENAME, [dataset])
            waitforkey()
            
@inlineCallbacks
def linearitycalibration(cxn):
    reg = cxn.registry
    fpga = cxn[FPGA_SERVER_NAME]
    fpganame = None
    while True:
        fpganame = yield selectdevice(fpga,
                         'Select a GHzDAC board to calibrate.',
                         'GHzDAC Board', default=fpganame)
        if fpganame == -1:
            return
        try: 
            yield reg.cd(['', keys.SESSIONNAME, fpganame], True)
            setup = yield reg.get(keys.IQWIRING)
        except:
            modifyHWparamsSingle(cxn, fpganame)
        clearscreen()
        if setup == keys.SETUPTYPES[0]:
            while True:
                choice = selectitem(['%s' % keys.CHANNELNAMES[0],
                                     '%s' % keys.CHANNELNAMES[1]],
                                    'Select a channel to calibrate on %s' \
                                    % fpganame)
                intorext10mhz = selectitem(['INT',
                                     'EXT'],
                                    'Select INT or EXT 10 MHz REF.')                                    
                if choice < 0:
                    break
                clearscreen()
                print
                print 'Measuring pulse response on %s' % fpganame
                print 
                print 'Connect:'
                print '    %s output           -->  SAMPLING SCOPE, channel %d' \
                      % (keys.CHANNELNAMES[choice], SCOPECHANNEL)

                print '    FPGA board S3+ output  -->  SAMPLING SCOPE, direct trigger input'
                print
                print 'Use the same cable length!'
                print

                if waitforkey():
                    break
                dataset = yield calibrateLinearity(cxn, fpganame, choice,intorext10mhz)
                yield reg.set(keys.CHANNELNAMES[choice], [dataset])
        else:
            zeroA, zeroB = yield zeroFixedCarrier(cxn, fpganame)
            print ''
            print 'Measuring pulse responses on %s' % fpganame
            print 'Connect:'
            print '    IQ mixer chain output  -->  SAMPLING SCOPE, channel %d' \
                  % SCOPECHANNEL
            print '    FPGA board S3+ output  -->  SAMPLING SCOPE, direct trigger input'
            print 'Use the same cable length!'
            print ''
            if waitforkey():
                continue
            dataset = yield calibrateACPulse(cxn, fpganame, zeroA, zeroB)
            yield reg.set(keys.PULSENAME, [dataset])
            waitforkey()
            


@inlineCallbacks
def zerosidebandcalibration(cxn, scanparams, zero=False, sideband=False):
    reg = cxn.registry
    fpga = cxn[FPGA_SERVER_NAME]
    alldevices = yield fpga.list_devices()
    devices = []
    for d in alldevices:
        print 'For d in alldevices: ',d
        try:
            yield reg.cd(['', keys.SESSIONNAME, d[1]], True)
            setup = yield reg.get(keys.IQWIRING)
            if setup != keys.SETUPTYPES[0]:
                devices.append(d[1])
        except:
            pass
    print devices
    getch()
    if not len(devices):
        print 
        print 'Found no GHzDAC boards with IQ mixer. Nothing to do.'
        getch()
        return

    devices = selectitems(devices, 'Select GHzDAC boards to calibrate')
    
    if devices == []:
        return
    clearscreen()
    print 
    print 'The following calibrations will be performed:'
    print
    print '  boards:' 
    for fpganame in devices:
        print '    ' + fpganame

    if zero:
        print
        print '  zero calibration:'
        print '    carrier frequencies from %.3g GHz to %.3g GHz in steps of %.3g MHz' % (scanparams['carrierMin'], scanparams['carrierMax'], scanparams['carrierStep'] * 1e3)
    if sideband:
        step = scanparams['sidebandFreqStep'] * 1000
        fmax = 0.5 * (scanparams['sidebandFreqCount']-1) * step
        print
        print '  sideband calibration:'
        print '    carrier frequencies from %.3g GHz to %.3g GHz in steps of %.3g MHz' % (scanparams['carrierMin'], scanparams['carrierMax'], scanparams['sidebandCarrierStep'] * 1e3)
        print '    sideband frequencies from %.3g MHz to %.3g MHz in steps of %.3g MHz' % (-fmax, fmax, step)
    print 
    print 'Estimated time: ' + timeestimate(scanparams, count=len(devices),
                                           sideband=sideband, zero=zero) + ' (no further interaction needed)'
    print
    if waitforkey():
        return
    for fpganame in devices:
        if zero:
            print fpganame
            dataset = yield zeroScanCarrier(cxn, scanparams, fpganame)
            yield reg.set(keys.ZERONAME, [dataset])
        if sideband:
            cor = yield IQcorrectorAsync(fpganame, cxn, iqcor=False)
            cor.dynamicReserve=4.0
            dataset = yield sidebandScanCarrier(cxn, scanparams, fpganame, cor)
            yield reg.set(keys.IQNAME, [dataset])
            



         
 

startReactor()
cxn = labrad.connect()
fpga = cxn[FPGA_SERVER_NAME]
anr = cxn.anritsu_server
spec = cxn.spectrum_analyzer_server
#scope = cxn.tektronix_5104b_oscilloscope()
reg  = cxn.registry
choice = 0
while choice >= 0:
    time.sleep(1)
    pulseCalTime = timeestimate(scanparams, pulse=True)
    zeroSidebandCalTime = timeestimate(scanparams, zero=True, sideband=True)
    zeroCalTime = timeestimate(scanparams, zero=True)
    sidebandCalTime = timeestimate(scanparams, sideband=True)
    choice = selectitem(['pulse calibration                     (%s per board)' % pulseCalTime,
                         'zero and sideband calibration         (%s per board)' % zeroSidebandCalTime,
                         'zero calibration only                 (%s per board)' % zeroCalTime,
                         'sideband calibration only             (%s per board)' % sidebandCalTime,
                         'change frequency ranges',
                         'change wiring parameters',
                         'measure linearity'],
                         'What do you want to do?')
    if choice == 0:
        pulsecalibration(cxn)
    elif choice == 1:
        zerosidebandcalibration(cxn, scanparams,
              zero=True, sideband=True)
    elif choice == 2:
        zerosidebandcalibration( cxn, scanparams, zero=True)
    elif choice == 3:
        zerosidebandcalibration( cxn, scanparams, sideband=True)
    elif choice == 4:
        scanparams = modifyfrequencyrange(scanparams)
    elif choice == 5:
        modifyHWparams( cxn)
    elif choice == 6:
        linearitycalibration(cxn)    
