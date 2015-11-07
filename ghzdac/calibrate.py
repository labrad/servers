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

# This module contains the calibration scripts. They must not require any
# user interaction because they are used not only for the initial
# calibration but also for recalibration. The user interface is provided
# by GHz_DAC_calibrate in "scripts".

import time
import numpy as np
import labrad
from labrad.types import Value
import keys

#trigger to be set:
#0x1: trigger S0
#0x2: trigger S1
#0x4: trigger S2
#0x8: trigger S3
#e.g. 0xA sets trigger S1 and S3
trigger = 0xFL << 28

FPGA_SERVER_NAME = 'ghz_fpgas'

DACMAX= 1 << 13 - 1
DACMIN= 1 << 13
PERIOD = 2000
SCOPECHANNEL_infiniium = 1
TRIGGERCHANNEL_infiniium = 2

SEQUENCE_LENGTH = 64


def assertSpecAnalLock(server, device):
    p = server.packet()
    p.select_device(device)
    p.query_10_mhz_ref(key='ref')
    ans = p.send()
    if ans['ref'] != 'EXT':
        raise Exception('Spectrum analyzer %s external 10MHz reference not locked!' %device)
        

def microwaveSourceServer(cxn, ID):
    anritsus = cxn.anritsu_server.list_devices()
    anritsus = [dev[1] for dev in anritsus]
    hittites = cxn.hittite_t2100_server.list_devices()
    hittites = [dev[1] for dev in hittites]
    if ID in anritsus:
        server = 'anritsu_server'
    elif ID in hittites:
        server = 'hittite_t2100_server'
    else:
        raise Exception('Microwave source %s not found' %ID)
    return (cxn.servers[server])
    

def validSBstep(f):
    return round(0.5*np.clip(f,2.0/PERIOD,1.0)*PERIOD)*2.0/PERIOD


def spectInit(spec):
    spec.gpib_write(':POW:RF:ATT 0dB;:AVER:STAT OFF;:FREQ:SPAN 100Hz;:BAND 300Hz;:INIT:CONT OFF;:SYST:PORT:IFVS:ENAB OFF;:SENS:SWE:POIN 101')

def spectDeInit(spec):
    spec.gpib_write(':INIT:CONT ON')
    
     
def spectFreq(spec,freq):
    spec.gpib_write(':FREQ:CENT %gGHz' % freq)

     
def signalPower(spec):
    """returns the mean power in mW read by the spectrum analyzer"""
    dBs = spec.gpib_query('*TRG;*OPC?;:TRAC:MATH:MEAN? TRACE1')
    dBs=dBs.split(';')[1]
    return (10.0**(0.1*float(dBs)))


def makeSample(a,b):
    """computes sram sample from dac A and B values"""
    if (np.max(a) > 0x1FFF) or (np.max(b) > 0x1FFF) or \
       (np.min(a) < -0x2000) or (np.min(b) < -0x2000):
        print 'DAC overflow'
    return long(a & 0x3FFFL) | (long(b & 0x3FFFL) << 14)

     
def measurePower(spec,fpga,a,b):
    """returns signal power from the spectrum analyzer"""
    dac = [makeSample(a,b)] * SEQUENCE_LENGTH
    dac[0] |= trigger
    # fpga.dac_run_sram(dac,True)
    fpga.dac_write_sram(dac)
    return ((signalPower(spec)))


def datasetNumber(dataset):
    return int(dataset[1][:5])


def datasetDir(dataset):
    result = ''
    dataset = dataset[0]+[dataset[1]]
    for s in dataset[1:]:
        result += " >> " + s
    return result


def minPos(l, c, r):
    """Calculates minimum of a parabola to three equally spaced points.
    The return value is in units of the spacing relative to the center point.
    It is bounded by -1 and 1.
    """
    d = l+r-2.0*c
    if d <= 0:
        return 0
    d = 0.5*(l-r)/d
    if d > 1:
        d = 1
    if d < -1:
        d = -1
    return d


####################################################################
# DAC zero calibration                                             #
####################################################################


def zero(anr, spec, fpga, freq):
    """Calibrates the zeros for DAC A and B using the spectrum analyzer"""
   
    anr.frequency(Value(freq,'GHz'))
    spectFreq(spec,freq)
    a = 0
    b = 0
    precision = 0x800
    print '    calibrating at %g GHz...' % freq
    while precision > 0:
        fpga.dac_run_sram([0] * SEQUENCE_LENGTH,  True)
        al = measurePower(spec, fpga, a-precision, b)
        ar = measurePower(spec, fpga, a+precision, b)
        ac = measurePower(spec, fpga, a, b)
        corra = long(round(precision*minPos(al, ac, ar)))
        a += corra

        bl = measurePower(spec, fpga, a, b-precision)
        br = measurePower(spec, fpga, a, b+precision)
        bc = measurePower(spec, fpga, a, b)
        corrb = long(round(precision*minPos(bl, bc, br)))
        b += corrb
        optprec = 2*np.max([abs(corra), abs(corrb)]) 
        precision /= 2
        if precision > optprec:
            precision = optprec
        print '        a = %4d  b = %4d uncertainty : %4d, power %6.1f dBm' % \
              (a, b, precision, 10 * np.log(bc) / np.log(10.0))
    return ([a, b])


def zeroFixedCarrier(cxn, boardname, use_switch=True):
    reg = cxn.registry
    reg.cd(['',keys.SESSIONNAME,boardname])

    fpga = cxn[FPGA_SERVER_NAME]
    fpga.select_device(boardname)

    if use_switch:
        switch = cxn.microwave_switch
        switch.switch(boardname)
    
    spec = cxn.spectrum_analyzer_server
    spectID = reg.get(keys.SPECTID)
    spec.select_device(spectID)
    spectInit(spec)
    assertSpecAnalLock(spec, spectID)
    uwaveSourceID = reg.get(keys.ANRITSUID)
    uwaveSource = microwaveSourceServer(cxn, uwaveSourceID)
    
    uwavePower = reg.get(keys.ANRITSUPOWER)
    frequency = (reg.get(keys.PULSECARRIERFREQ))['GHz']
    uwaveSource.select_device(uwaveSourceID)
    uwaveSource.amplitude(uwavePower)
    uwaveSource.output(True)

    print 'Zero calibration...'

    daczeros = zero(uwaveSource, spec, fpga, frequency)

    uwaveSource.output(False)
    spectDeInit(spec)
    if use_switch:
        switch.switch(0)
    return daczeros



def zeroScanCarrier(cxn, scanparams, boardname, use_switch=True):
    """Measures the DAC zeros in function of the carrier frequency."""
    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, boardname])

    fpga = cxn[FPGA_SERVER_NAME]
    fpga.select_device(boardname)

    if use_switch:
        switch = cxn.microwave_switch
        switch.switch(boardname)
    
    spec = cxn.spectrum_analyzer_server
    spectID = reg.get(keys.SPECTID)
    spec.select_device(spectID)
    spectInit(spec)
    assertSpecAnalLock(spec, spectID)
    uwaveSourceID = reg.get(keys.ANRITSUID)
    uwaveSource = microwaveSourceServer(cxn, uwaveSourceID)
    uwavePower = reg.get(keys.ANRITSUPOWER)
    uwaveSource.select_device(uwaveSourceID)
    uwaveSource.amplitude(uwavePower)
    uwaveSource.output(True)

    print 'Zero calibration from %g GHz to %g GHz in steps of %g GHz...' % \
        (scanparams['carrierMin'],scanparams['carrierMax'],scanparams['carrierStep'])
    ds = cxn.data_vault
    ds.cd(['', keys.SESSIONNAME, boardname], True)
    dataset = ds.new(keys.ZERONAME,
                           [('Frequency', 'GHz')],
                           [('DAC zero', 'A', 'clics'),
                            ('DAC zero', 'B', 'clics')])
    ds.add_parameter(keys.ANRITSUPOWER, uwavePower)

    freq = scanparams['carrierMin']
    while freq < scanparams['carrierMax']+0.001*scanparams['carrierStep']:
        ds.add([freq]+(zero(uwaveSource, spec, fpga, freq)))
        freq += scanparams['carrierStep']
    uwaveSource.output(False)
    spectDeInit(spec)
    if use_switch:
        cxn.microwave_switch.switch(0)
    return (int(dataset[1][:5]))
                
####################################################################
# Pulse calibration                                                #
####################################################################


def measureImpulseResponse(fpga, scope, baseline, pulse, dacoffsettime=6, pulselength=1):
    """Measure the response to a DAC pulse
    fpga: connected fpga server
    scope: connected scope server
    dac: 'a' or 'b'
    returns: list
    list[0] : start time (s)
    list[1] : time step (s)
    list[2:]: actual data (V)
    """
    #units clock cycles
    dacoffsettime = int(round(dacoffsettime))
    triggerdelay = 30
    looplength = 2000
    pulseindex = triggerdelay-dacoffsettime
    scope.start_time(Value(triggerdelay, 'ns'))
    #calculate the baseline voltage by capturing a trace without a pulse
    
    data = np.resize(baseline, looplength)
    data[pulseindex:pulseindex+pulselength] = pulse
    data[0] |= trigger
    fpga.dac_run_sram(data.astype('u4'),True)
    data = (scope.get_trace(1))
    data[0] -= Value(triggerdelay*1e-9, 'V')  # TODO: not sure about units here--pjjo
    return (data)


def measureImpulseResponse_infiniium(fpga, scope, baseline, pulse,
                                     dacoffsettime=6, pulselength=1, wait=75, looplength=6000):
    """Measure the response to a DAC pulse
    looplength: time between triggers, keep this above pulselength , 6000 for short dacs
    fpga: connected fpga server
    scope: connected scope server
    dac: 'a' or 'b'
    returns: list
    list[0] : start time (s)
    list[1] : time step (s)
    list[2:]: actual data (V)
    """
    #units clock cycles
    dacoffsettime = int(round(dacoffsettime))
    triggerdelay = 30 #keep at least at 30
    pulseindex = triggerdelay-dacoffsettime

    data = np.resize(baseline, looplength)
    data[pulseindex:pulseindex+pulselength] = pulse
    data[0] |= trigger
    fpga.dac_run_sram(data,True)
    if wait:
        time.sleep(wait) #keep this long enough!! 40 sec for 4096, 20 sec for 2048

    t, y = scope.get_trace(SCOPECHANNEL_infiniium) #start and stop in ns

    # Truncate data before t=0
    after_zero_idx = np.argwhere(t > 0).flatten()
    t = t[after_zero_idx]
    y = y[after_zero_idx]

    return t, y


def calibrateACPulse(cxn, boardname, baselineA, baselineB, use_switch=True):
    """Measures the impulse response of the DACs after the IQ mixer"""
    pulseheight = 0x1800

    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, boardname])

    if use_switch:
        switch = cxn.microwave_switch

    uwaveSourceID = reg.get(keys.ANRITSUID)    
    uwaveSource = microwaveSourceServer(cxn,uwaveSourceID)
    uwaveSourcePower = reg.get(keys.ANRITSUPOWER)
    carrierFreq = reg.get(keys.PULSECARRIERFREQ)
    sens = reg.get(keys.SCOPESENSITIVITY)
    offs = reg.get(keys.SCOPEOFFSET, True, Value(0, 'mV'))
    if use_switch:
        switch.switch(boardname) #Hack to select the correct microwave switch
        switch.switch(0)
    uwaveSource.select_device(uwaveSourceID)
    uwaveSource.frequency(carrierFreq)
    uwaveSource.amplitude(uwaveSourcePower)
    uwaveSource.output(True)
    
    #Set up the scope
    scope = cxn.sampling_scope
    scopeID = reg.get(keys.SCOPEID)
    scope.select_device(scopeID)
    p = scope.packet().\
    reset().\
    channel(reg.get(keys.SSCOPECHANNEL, True, 2)).\
    trace(1).\
    record_length(5120L).\
    average(128).\
    sensitivity(sens).\
    offset(offs).\
    time_step(Value(2,'ns')).\
    trigger_level(Value(0.18,'V')).\
    trigger_positive()
    p.send()

    fpga = cxn[FPGA_SERVER_NAME]
    fpga.select_device(boardname)
    offsettime = reg.get(keys.TIMEOFFSET)

    baseline = makeSample(baselineA,baselineB)
#    print "Measuring offset voltage..."
#    offset = (measureImpulseResponse(fpga, scope, baseline, baseline))[2:]
#    offset = sum(offset) / len(offset)

    print "Measuring pulse response DAC A..."
    traceA = measureImpulseResponse(fpga, scope, baseline,
        makeSample(baselineA+pulseheight,baselineB),
        dacoffsettime=offsettime['ns'])

    print "Measuring pulse response DAC B..."
    traceB = measureImpulseResponse(fpga, scope, baseline,
        makeSample(baselineA,baselineB+pulseheight),
        dacoffsettime=offsettime['ns'])

    starttime = traceA[0]
    timestep = traceA[1]
    if (starttime != traceB[0]) or (timestep != traceB[1]) :
        print """Time scales are different for measurement of DAC A and B.
        Did you change settings on the scope during the measurement?"""
        exit
    #set output to zero
    fpga.dac_run_sram([baseline]*20)
    uwaveSource.output(False)
    ds = cxn.data_vault
    ds.cd(['',keys.SESSIONNAME,boardname],True)
    dataset = ds.new(keys.PULSENAME,[('Time','ns')],
                           [('Voltage','A','V'),('Voltage','B','V')])
    setupType = reg.get(keys.IQWIRING)
    ds.add_parameter(keys.IQWIRING, setupType)
    ds.add_parameter(keys.PULSECARRIERFREQ, carrierFreq)
    ds.add_parameter(keys.ANRITSUPOWER, uwaveSourcePower)
    ds.add_parameter(keys.TIMEOFFSET, offsettime)
    # begin unit strip party
    starttime = starttime[starttime.unit]  # stripping units
    timestep = timestep[timestep.unit]  # stripping units
    traceA = traceA[traceA.unit]  # stripping units
    traceB = traceB[traceB.unit]  # stripping units
    data = np.transpose(\
        [1e9*(starttime+timestep*np.arange(np.alen(traceA)-2)),
         traceA[2:],traceB[2:]])
    ds.add(data)
#        traceA[2:]-offset,
#        traceB[2:]-offset]))
    if np.abs(np.argmax(np.abs(traceA-np.average(traceA))) - \
                 np.argmax(np.abs(traceB-np.average(traceB)))) \
       * timestep > 0.5e-9:
        print "Pulses from DAC A and B do not seem to be on top of each other!"
        print "Sideband calibrations based on this pulse calibration will"
        print "most likely mess up you sequences!"
    print
    print "Check the following pulse calibration file in the data vault:"
    print datasetDir(dataset)
    print "If the pulses are offset by more than 0.5 ns,"
    print "bring up the board and try the pulse calibration again."
    print 5
    return (datasetNumber(dataset))


def calibrateDCPulse(cxn,boardname,channel):

    reg = cxn.registry
    reg.cd(['',keys.SESSIONNAME,boardname])

    fpga = cxn[FPGA_SERVER_NAME]
    fpga.select_device(boardname)

    dac_baseline = -0x2000
    dac_pulse = 0x1FFF
    dac_neutral = 0x0000
    if channel:
        pulse = makeSample(dac_neutral, dac_pulse)
        baseline = makeSample(dac_neutral, dac_baseline)
    else:
        pulse = makeSample(dac_pulse, dac_neutral)
        baseline = makeSample(dac_baseline, dac_neutral)
    #Set up the scope
    scope = cxn.sampling_scope
    scopeID = reg.get(keys.SCOPEID)
    print "scopeID:", scopeID
    p = scope.packet().\
    select_device(scopeID).\
    reset().\
    channel(reg.get(keys.SSCOPECHANNEL, True, 2)).\
    trace(1).\
    record_length(5120).\
    average(128).\
    sensitivity(reg.get(keys.SSCOPESENSITIVITYDC, True, 200*labrad.units.mV)).\
    offset(Value(0,'mV')).\
    time_step(Value(5,'ns')).\
    trigger_level(Value(0.18,'V')).\
    trigger_positive()
    p.send()

    offsettime = reg.get(keys.TIMEOFFSET)

    

    print 'Measuring step response...'
    trace = measureImpulseResponse(fpga, scope, baseline, pulse,
        dacoffsettime=offsettime['ns'], pulselength=100)
    trace = trace[trace.unit]  # strip units
    # set the output to zero so that the fridge does not warm up when the
    # cable is plugged back in
    fpga.dac_run_sram([makeSample(dac_neutral, dac_neutral)]*20, False)
    ds = cxn.data_vault
    ds.cd(['', keys.SESSIONNAME, boardname],True)
    dataset = ds.new(keys.CHANNELNAMES[channel], [('Time','ns')],
                           [('Voltage','','V')])
    ds.add_parameter(keys.TIMEOFFSET, offsettime)
    ds.add(np.transpose([1e9*(trace[0]+trace[1]*np.arange(np.alen(trace)-2)),
        trace[2:]]))
    return (datasetNumber(dataset))


def calibrateDCPulse_infiniium(cxn, boardname, channel, conf_10_MHz):

    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME,boardname])

    fpga = cxn[FPGA_SERVER_NAME]
    fpga.select_device(boardname)

    dac_baseline = 0x000
    dac_pulse = 0x1000
    dac_neutral = 0x0000
    if channel:
        pulse = makeSample(dac_neutral,dac_pulse)
        baseline = makeSample(dac_neutral, dac_baseline)
    else:
        pulse = makeSample(dac_pulse, dac_neutral)
        baseline = makeSample(dac_baseline, dac_neutral)
    scope = cxn.agilent_infiniium_oscilloscope()
    scope.select_device()

    scope.reset()
    print 'scope reset'

    fpga.dac_run_sram([makeSample(dac_neutral, dac_neutral)]*4,False) #set DAC to zero BEFORE setting the scope to acquire
    time.sleep(2)

    numberofaverages=4096

    p = scope.packet().\
    gpib_write('TIM:REFC '+str(conf_10_MHz)).\
    channelonoff(SCOPECHANNEL_infiniium, 'ON').\
    channelonoff(TRIGGERCHANNEL_infiniium, 'ON').\
    scale(SCOPECHANNEL_infiniium, 0.1).\
    scale(TRIGGERCHANNEL_infiniium, 0.5).\
    position(SCOPECHANNEL_infiniium, 0.02).\
    position(TRIGGERCHANNEL_infiniium,0.0).\
    horiz_scale(500.0e-9).\
    horiz_position(0.0).\
    trigger_sweep('TRIG').\
    trigger_mode('EDGE').\
    trigger_edge_slope('POS').\
    trigger_at(TRIGGERCHANNEL_infiniium, 1.0).\
    averagemode(1).\
    numavg(numberofaverages)

    p.send()
    print 'scope packet sent'
    time.sleep(1)
    ref_10_MHz = scope.gpib_query(':TIM:REFC?')

    if ref_10_MHz == '1':
        ref_str_rep = 'EXT'
    else:
        ref_str_rep = 'INT'
    print '10 MHz ref: ' + ref_str_rep

    offsettime = reg.get(keys.TIMEOFFSET)

    print 'Measuring step response...'
    t, y = measureImpulseResponse_infiniium(fpga, scope, baseline, pulse,
                                             dacoffsettime=offsettime['ns'], pulselength=3000, looplength=6000)

    # set the output to zero so that the fridge does not warm up when the
    # cable is plugged back in
    fpga.dac_run_sram([makeSample(dac_neutral, dac_neutral)]*4,False)
    ds = cxn.data_vault
    ds.cd(['', keys.SESSIONNAME, boardname],True)
    dataset = ds.new(keys.CHANNELNAMES[channel], [('Time', 'ns')],
                           [('Voltage', '', 'V')])
    ds.add_parameter(keys.TIMEOFFSET, offsettime)
    ds.add_parameter('dac baseline', dac_baseline)
    ds.add_parameter('dac pulse', dac_pulse)
    ds.add_parameter('10 MHz ref', ref_str_rep)
    ds.add_parameter('scope', 'Agilent13GHz')
    ds.add_parameter('stats', numberofaverages)
    ds.add(np.vstack((t['ns'], y['V'])).transpose())
    return datasetNumber(dataset)


####################################################################
# Sideband calibration                                             #
####################################################################

 
def measureOppositeSideband(spec, fpga, corrector,
                            carrierfreq, sidebandfreq, compensation):
    """Put out a signal at carrierfreq+sidebandfreq and return the power at
    carrierfreq-sidebandfreq"""

    arg = -2.0j*np.pi*sidebandfreq*np.arange(PERIOD)
    signal = corrector.DACify(carrierfreq,
                            0.5 * np.exp(arg) + 0.5 * compensation * np.exp(-arg),
                            loop=True, iqcor=False, rescale=True)
    for i in range(4):
        signal[i] |= trigger
    fpga.dac_run_sram(signal, True)
    return ((signalPower(spec)) / corrector.last_rescale_factor)

 
def sideband(anr, spect, fpga, corrector, carrierfreq, sidebandfreq):
    """When the IQ mixer is used for sideband mixing, imperfections in the
    IQ mixer and the DACs give rise to a signal not only at
    carrierfreq+sidebandfreq but also at carrierfreq-sidebandfreq.
    This routine determines amplitude and phase of the sideband signal
    for carrierfreq-sidebandfreq that cancels the undesired sideband at
    carrierfreq-sidebandfreq."""
    reserveBuffer = corrector.dynamicReserve
    corrector.dynamicReserve = 4.0

    if abs(sidebandfreq) < 3e-5:
        return (0.0j)
    anr.frequency(Value(carrierfreq,'GHz'))
    comp = 0.0j
    precision = 1.0
    spectFreq(spect,carrierfreq-sidebandfreq)
    while precision > 2.0**-14:
        fpga.dac_run_sram(np.array([0] * PERIOD, dtype='<u4'), True)
        lR = measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp - precision)
        rR = measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp + precision)
        cR = measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp)
        
        corrR = precision * minPos(lR,cR,rR)
        comp += corrR
        lI = measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp - 1.0j * precision)
        rI = measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp + 1.0j * precision)
        cI = measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp)
        
        corrI = precision * minPos(lI,cI,rI)
        comp += 1.0j * corrI
        precision = np.min([2.0 * np.max([abs(corrR),abs(corrI)]), precision / 2.0])
        print '      compensation: %.4f%+.4fj +- %.4f, opposite sb: %6.1f dBm' % \
            (np.real(comp), np.imag(comp), precision, 10.0 * np.log(cI) / np.log(10.0))
    corrector.dynamicReserve = reserveBuffer
    return (comp)


def sidebandScanCarrier(cxn, scanparams, boardname, corrector, use_switch=True):
    """Determines relative I and Q amplitudes by canceling the undesired
       sideband at different sideband frequencies."""

    reg = cxn.registry
    reg.cd(['', keys.SESSIONNAME, boardname])

    fpga = cxn[FPGA_SERVER_NAME]
    fpga.select_device(boardname)

    uwaveSourceID = reg.get(keys.ANRITSUID)
    uwaveSource = microwaveSourceServer(cxn, uwaveSourceID)

    spec = cxn.spectrum_analyzer_server
    ds = cxn.data_vault
    spectID = reg.get(keys.SPECTID)
    spec.select_device(spectID)
    spectInit(spec)
    assertSpecAnalLock(spec, spectID)
    
    uwaveSourcePower = reg.get(keys.ANRITSUPOWER)
    if use_switch:
        cxn.microwave_switch.switch(boardname)
    uwaveSource.select_device(uwaveSourceID)
    uwaveSource.amplitude(uwaveSourcePower)
    uwaveSource.output(True)

    print 'Sideband calibration from %g GHz to %g GHz in steps of %g GHz...' \
       %  (scanparams['carrierMin'],scanparams['carrierMax'],
           scanparams['sidebandCarrierStep'])
    
    sidebandfreqs = (np.arange(scanparams['sidebandFreqCount']) \
                         - (scanparams['sidebandFreqCount']-1) * 0.5) \
                     * validSBstep(scanparams['sidebandFreqStep'])
    dependents = []
    for sidebandfreq in sidebandfreqs:
        dependents += [('relative compensation', 'Q at f_SB = %g MHz' % \
                            (sidebandfreq*1e3),''),
                       ('relative compensation', 'I at f_SB = %g MHz' % \
                            (sidebandfreq*1e3),'')]    
    ds.cd(['', keys.SESSIONNAME, boardname], True)
    dataset = ds.new(keys.IQNAME, [('Antritsu Frequency','GHz')], dependents)
    ds.add_parameter(keys.ANRITSUPOWER, (reg.get(keys.ANRITSUPOWER)))
    ds.add_parameter('Sideband frequency step',
                     Value(scanparams['sidebandFreqStep']*1e3, 'MHz'))
    ds.add_parameter('Number of sideband frequencies',
                     scanparams['sidebandFreqCount'])
    freq = scanparams['carrierMin']
    while freq < scanparams['carrierMax'] + \
              0.001 * scanparams['sidebandCarrierStep']:
        print '  carrier frequency: %g GHz' % freq
        datapoint = [freq]
        for sidebandfreq in sidebandfreqs:
            print '    sideband frequency: %g GHz' % sidebandfreq
            comp = sideband(uwaveSource, spec, fpga, corrector, freq, sidebandfreq)
            datapoint += [np.real(comp), np.imag(comp)]
        ds.add(datapoint)
        freq += scanparams['sidebandCarrierStep']
    uwaveSource.output(False)
    spectDeInit(spec)
    if use_switch:
        cxn.microwave_switch.switch(0)
    return (datasetNumber(dataset))
