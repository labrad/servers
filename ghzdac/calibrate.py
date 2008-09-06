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

from ghzdac import IQcorrector
import keys
from numpy import exp, pi, arange, real, imag, min, max, log, transpose, alen, resize
from labrad.types import Value
from datetime import datetime
from twisted.internet.defer import inlineCallbacks, returnValue
#trigger to be set:
#0x1: trigger S0
#0x2: trigger S1
#0x4: trigger S2
#0x8: trigger S3
#e.g. 0xA sets trigger S1 and S3
trigger = 0xFL << 28

DACMAX= 1 << 13 - 1
DACMIN= 1 << 13
PERIOD = 200
SBFREQUNIT = 1.0/PERIOD

@inlineCallbacks
def spectInit(spec):
    yield spec.gpib_write(':POW:RF:ATT 0dB;:AVER:STAT OFF;:FREQ:SPAN 100Hz;:BAND 300Hz;:INIT:CONT OFF;:SYST:PORT:IFVS:ENAB OFF;:SENS:SWE:POIN 101')

def spectDeInit(spec):
    yield spec.gpib_write(':INIT:CONT ON')
    
@inlineCallbacks     
def spectFreq(spec,freq):
    yield spec.gpib_write(':FREQ:CENT %gGHz' % freq)

@inlineCallbacks     
def signalPower(spec):
    """returns the mean power in mW read by the spectrum analyzer"""
    dBs = yield spec.gpib_query('*TRG;*OPC?;:TRAC:MATH:MEAN? TRACE1')
    returnValue(10.0**(0.1*float(dBs[3:])))


def makeSample(a,b):
    """computes sram sample from dac A and B values"""
    if (max(a) > 0x1FFF) or (max(b) > 0x1FFF) or (min(a) < -0x2000) or (min(b) < -0x2000):
        print 'DAC overflow'
    return long(a & 0x3FFFL) | (long(b & 0x3FFFL) << 14)

@inlineCallbacks     
def measurePower(spec,fpga,a,b):
    """returns signal power from the spectrum analyzer"""
    dac=[makeSample(a,b)]*64
    dac[0] |= trigger
    yield fpga.run_sram(dac,True)
    returnValue((yield signalPower(spec)))

def datasetNumber(dataset):
    return int(dataset[1][:5])

def minPos(l,c,r):
    """Calculates minimum of a parabola to three equally spaced points.
    The return value is in units of the spacing relative to the center point.
    It is bounded by -1 and 1.
    """
    d=l+r-2.0*c
    if d <= 0:
        return 0
    d=0.5*(l-r)/d
    if d>1:
        d=1
    if d<-1:
        d=-1
    return d


####################################################################
# DAC zero calibration                                             #
####################################################################

  
@inlineCallbacks 
def zero(anr, spec, fpga, freq):
    """Calibrates the zeros for DAC A and B using the spectrum analyzer"""
   
    yield anr.frequency(Value(freq,'GHz'))
    yield spectFreq(spec,freq)
    a=0
    b=0
    precision=0x800
    print '    calibrating at %g GHz...' % freq
    while precision > 0:
        al = yield measurePower(spec,fpga,a-precision,b)
        ar = yield measurePower(spec,fpga,a+precision,b)
        ac = yield measurePower(spec,fpga,a,b)
        corra=long(round(precision*minPos(al,ac,ar)))
        a+=corra

        bl = yield measurePower(spec,fpga,a,b-precision)
        br = yield measurePower(spec,fpga,a,b+precision)
        bc = yield measurePower(spec,fpga,a,b)
        corrb=long(round(precision*minPos(bl,bc,br)))
        b+=corrb
        optprec=2*max([abs(corra),abs(corrb)]) 
        precision/=2
        if precision>optprec:
            precision=optprec
        print '        a = %4d  b = %4d uncertainty : %4d, power %6.1f dBm' % \
              (a, b, precision, 10 * log(bc) / log(10.0))
    returnValue([a,b])

@inlineCallbacks
def zeroFixedCarrier(cxn, boardname):
    fpga = cxn.ghz_dacs
    yield fpga.select_device(boardname)
    yield cxn.microwave_switch.switch(boardname)
    anr = cxn.anritsu_server
    spec = cxn.spectrum_analyzer_server
    
    reg = cxn.registry
    yield reg.cd(['',keys.SESSIONNAME,boardname])
    spectID = yield reg.get(keys.SPECTID)
    spec.select_device(spectID)
    yield spectInit(spec)

    anritsuID = yield reg.get(keys.ANRITSUID)
    anritsuPower = yield reg.get(keys.ANRITSUPOWER)
    frequency = (yield reg.get(keys.PULSECARRIERFREQ))['GHz']
    yield anr.select_device(anritsuID)
    yield anr.amplitude(anritsuPower)
    yield anr.output(True)

    print 'Zero calibration...'

    daczeros = yield zero(anr,spec,fpga,frequency)

    yield anr.output(False)
    yield spectDeInit(spec)
    yield cxn.microwave_switch.switch(0)
    returnValue(daczeros)
    


@inlineCallbacks
def zeroScanCarrier(cxn, scanparams, boardname):
    """Measures the DAC zeros in function of the carrier frequency."""
    fpga = cxn.ghz_dacs
    yield fpga.select_device(boardname)
    yield cxn.microwave_switch.switch(boardname)
    anr = cxn.anritsu_server
    spec = cxn.spectrum_analyzer_server
    reg = cxn.registry
    yield reg.cd(['',keys.SESSIONNAME,boardname])
    spectID = yield reg.get(keys.SPECTID)
    spec.select_device(spectID)
    yield spectInit(spec)

    anritsuID = yield reg.get(keys.ANRITSUID)
    anritsuPower = yield reg.get(keys.ANRITSUPOWER)
    yield anr.select_device(anritsuID)
    yield anr.amplitude(anritsuPower)
    yield anr.output(True)

    print 'Zero calibration from %g GHz to %g GHz in steps of %g GHz...' % \
        (scanparams['carrierMin'],scanparams['carrierMax'],scanparams['carrierStep'])

    ds = cxn.data_vault
    yield ds.cd(['',keys.SESSIONNAME,boardname],True)
    dataset = yield ds.new(keys.ZERONAME,
                           [('Frequency','GHz')],
                           [('DAC zero', 'A', 'clics'),
                            ('DAC zero', 'B', 'clics')])
    yield ds.add_parameter(keys.ANRITSUPOWER, anritsuPower)

    freq=scanparams['carrierMin']
    while freq<scanparams['carrierMax']:
        yield ds.add([freq]+(yield zero(anr,spec,fpga,freq)))
        freq+=scanparams['carrierStep']
    yield anr.output(False)
    yield spectDeInit(spec)
    yield cxn.microwave_switch.switch(0)
    returnValue(int(dataset[1][:5]))
                
####################################################################
# Pulse calibration                                                #
####################################################################

@inlineCallbacks
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
    triggerdelay=30
    looplength=2000
    pulseindex=triggerdelay-dacoffsettime
    yield scope.start_time(Value(triggerdelay,'ns'))
    #calculate the baseline voltage by capturing a trace without a pulse

    data = resize(baseline, looplength)
    data[pulseindex:pulseindex+pulselength] = pulse
    data[0] |= trigger
    yield fpga.run_sram(data,True)
    data = (yield scope.get_trace(1)).asarray
    data[0]-=triggerdelay*1e-9
    returnValue(data)

@inlineCallbacks
def calibrateACPulse(cxn, boardname, baselineA, baselineB):
    """Measures the impulse response of the DACs after the IQ mixer"""
    pulseheight=0x1800

    reg = cxn.registry
    yield reg.cd(['',keys.SESSIONNAME,boardname])

    anr = cxn.anritsu_server
    anritsuID = yield reg.get(keys.ANRITSUID)
    anritsuPower = yield reg.get(keys.ANRITSUPOWER)
    carrierFreq = yield reg.get(keys.PULSECARRIERFREQ)
    yield cxn.microwave_switch.switch(0)
    yield anr.select_device(anritsuID)
    yield anr.frequency(carrierFreq)
    yield anr.amplitude(anritsuPower)
    yield anr.output(True)
    
    #Set up the scope
    scope = cxn.sampling_scope
    scopeID = yield reg.get(keys.SCOPEID)
    yield scope.select_device(scopeID)
    p = scope.packet().\
    reset().\
    channel(1).\
    trace(1).\
    record_length(5120).\
    average(128).\
    sensitivity(Value(10.0,'mV')).\
    offset(Value(0,'mV')).\
    time_step(Value(2,'ns')).\
    trigger_level(Value(0.18,'V')).\
    trigger_positive()
    yield p.send()

    fpga = cxn.ghz_dacs
    yield fpga.select_device(boardname)
    offsettime = yield reg.get(keys.TIMEOFFSET)

    baseline = makeSample(baselineA,baselineB)
    print "Measuring offset voltage..."
    offset = (yield measureImpulseResponse(fpga, scope, baseline, baseline))[2:]
    offset = sum(offset) / len(offset)

    print "Measuring pulse response DAC A..."
    traceA = yield measureImpulseResponse(fpga, scope, baseline,
        makeSample(baselineA+pulseheight,baselineB),
        dacoffsettime=offsettime['ns'])

    print "Measuring pulse response DAC B..."
    traceB = yield measureImpulseResponse(fpga, scope, baseline,
        makeSample(baselineA,baselineB+pulseheight),
        dacoffsettime=offsettime['ns'])

    starttime = traceA[0]
    timestep = traceA[1]
    if (starttime != traceB[0]) or (timestep != traceB[1]) :
        print """Time scales are different for measurement of DAC A and B.
        Did you change settings on the scope during the measurement?"""
        exit
    #set output to zero    
    yield fpga.run_sram([baseline]*4)
    yield anr.output(False)
    ds = cxn.data_vault
    yield ds.cd(['',keys.SESSIONNAME,boardname],True)
    dataset = yield ds.new(keys.PULSENAME,[('Time','ns')],
                           [('Voltage','A','V'),('Voltage','B','V')])
    setupType = yield reg.get(keys.IQWIRING)
    yield ds.add_parameter(keys.IQWIRING, setupType)
    yield ds.add_parameter(keys.PULSECARRIERFREQ, carrierFreq)
    yield ds.add_parameter(keys.ANRITSUPOWER, anritsuPower)
    yield ds.add_parameter(keys.TIMEOFFSET, offsettime)
    yield ds.add(transpose([1e9*(starttime+timestep*arange(alen(traceA)-2)),
        traceA[2:]-offset,
        traceB[2:]-offset]))
    returnValue(datasetNumber(dataset))

@inlineCallbacks
def calibrateDCPulse(cxn,boardname,channel):

    reg = cxn.registry
    yield reg.cd(['',keys.SESSIONNAME,boardname])

    fpga = cxn.ghz_dacs
    fpga.select_device(boardname)

    dac_baseline = -0x2000
    dac_pulse=0x1FFF
    dac_neutral = 0x0000
    if channel:
        pulse = makeSample(dac_neutral,dac_pulse)
        baseline = makeSample(dac_neutral, dac_baseline)
    else:
        pulse = makeSample(dac_pulse, dac_neutral)
        baseline = makeSample(dac_baseline, dac_neutral)
    #Set up the scope
    scope = cxn.sampling_scope
    scopeID = yield reg.get(keys.SCOPEID)
    p = scope.packet().\
    select_device(scopeID).\
    reset().\
    channel(1).\
    trace(1).\
    record_length(5120).\
    average(128).\
    sensitivity(Value(100.0,'mV')).\
    offset(Value(0,'mV')).\
    time_step(Value(5,'ns')).\
    trigger_level(Value(0.18,'V')).\
    trigger_positive()
    yield p.send()

    offsettime = yield reg.get(keys.TIMEOFFSET)

    

    print 'Measuring step response...'
    trace = yield measureImpulseResponse(fpga, scope, baseline, pulse,
        dacoffsettime=offsettime['ns'],pulselength=100)
    # set the output to zero so that the fridge does not warm up when the
    # cable is plugged back in
    yield fpga.run_sram([makeSample(dac_neutral, dac_neutral)]*4,False)
    ds = cxn.data_vault
    yield ds.cd(['',keys.SESSIONNAME,boardname],True)
    dataset = yield ds.new(keys.CHANNELNAMES[channel],[('Time','ns')],
                           [('Voltage','','V')])
    yield ds.add_parameter(keys.TIMEOFFSET, offsettime)
    yield ds.add(transpose([1e9*(trace[0]+trace[1]*arange(alen(trace)-2)),
        trace[2:]]))
    returnValue(datasetNumber(dataset))


####################################################################
# Sideband calibration                                             #
####################################################################

@inlineCallbacks 
def measureOppositeSideband(spec, fpga, corrector,
                            carrierfreq, sidebandfreq, compensation):
    """Put out a signal at carrierfreq+sidebandfreq and return the power at
    carrierfreq-sidebandfreq"""

    arg=-2.0j*pi*sidebandfreq*arange(PERIOD)
    signal=corrector.DACify(carrierfreq,
                            0.5 * exp(arg) + 0.5 * compensation * exp(-arg), \
                            loop=True, iqcor=False, rescale=True)
    signal[0] = signal[0] | trigger
    yield fpga.run_sram(signal,True)
    returnValue((yield signalPower(spec)) / corrector.last_rescale_factor)

@inlineCallbacks 
def sideband(anr,spect,fpga,corrector,carrierfreq,sidebandfreq):
    """When the IQ mixer is used for sideband mixing, imperfections in the
    IQ mixer and the DACs give rise to a signal not only at
    carrierfreq+sidebandfreq but also at carrierfreq-sidebandfreq.
    This routine determines amplitude and phase of the sideband signal
    for carrierfreq-sidebandfreq that cancels the undesired sideband at
    carrierfreq-sidebandfreq."""
    reserveBuffer = corrector.dynamicReserve
    corrector.dynamicReserve = 4.0

    if abs(sidebandfreq) < 3e-5:
        returnValue(0.0j)
    yield anr.frequency(Value(carrierfreq,'GHz'))
    comp=0.0j
    precision=1.0
    yield spectFreq(spect,carrierfreq-sidebandfreq)
    while precision > 2.0**-14:
        lR = yield measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp - precision)
        rR = yield measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp + precision)
        cR = yield measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp)
        
        corrR = precision * minPos(lR,cR,rR)
        comp += corrR
        lI = yield measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp - 1.0j * precision)
        rI = yield measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp + 1.0j * precision)
        cI = yield measureOppositeSideband(spect, fpga, corrector, carrierfreq,
                                           sidebandfreq, comp)
        
        corrI = precision * minPos(lI,cI,rI)
        comp += 1.0j * corrI
        precision=min([2.0 * max([abs(corrR),abs(corrI)]), precision / 2.0])
        print '      compensation: %.4f%+.4fj +- %.4f, opposite sb: %6.1f dBm' % \
            (real(comp), imag(comp), precision, 10.0 * log(cI) / log(10.0))
    corrector.dynamicReserve = reserveBuffer
    returnValue(comp)

@inlineCallbacks
def sidebandScanCarrier(cxn, scanparams, boardname, corrector):
    """Determines relative I and Q amplitudes by canceling the undesired
       sideband at different sideband frequencies."""

    fpga=cxn.ghz_dacs
    yield fpga.select_device(boardname)
    anr=cxn.anritsu_server
    spec=cxn.spectrum_analyzer_server
    scope=cxn.sampling_scope
    ds=cxn.data_vault
    reg = cxn.registry
    yield reg.cd(['',keys.SESSIONNAME,boardname])
    spectID = yield reg.get(keys.SPECTID)
    spec.select_device(spectID)
    yield spectInit(spec)

    anritsuID = yield reg.get(keys.ANRITSUID)
    anritsuPower = yield reg.get(keys.ANRITSUPOWER)
    yield cxn.microwave_switch.switch(boardname)
    yield anr.select_device(anritsuID)
    yield anr.amplitude(anritsuPower)
    yield anr.output(True)

    print 'Sideband calibration from %g GHz to %g GHz in steps of %g GHz...' \
       %  (scanparams['carrierMin'],scanparams['carrierMax'],
           scanparams['sidebandCarrierStep'])
    
    sidebandfreqs = (arange(scanparams['sidebandFreqCount']) \
                         - (scanparams['sidebandFreqCount']-1) * 0.5) \
                     * scanparams['sidebandFreqStep']
    dependents = []
    for sidebandfreq in sidebandfreqs:
        dependents += [('relative compensation', 'Q at f_SB = %g MHz' % \
                            (sidebandfreq*1e3),''),
                       ('relative compensation', 'I at f_SB = %g MHz' % \
                            (sidebandfreq*1e3),'')]    
    yield ds.cd(['',keys.SESSIONNAME,boardname],True)
    dataset = yield ds.new(keys.IQNAME,[('Antritsu Frequency','GHz')],dependents)
    yield ds.add_parameter(keys.ANRITSUPOWER, (yield reg.get(keys.ANRITSUPOWER)))
    yield ds.add_parameter('Sideband frequency step',
                     Value(scanparams['sidebandFreqStep']*1e3,'MHz'))
    yield ds.add_parameter('Number of sideband frequencies',
                     scanparams['sidebandFreqCount'])
    freq=scanparams['carrierMin']
    while freq<scanparams['carrierMax']:
        print '  carrier frequency: %g GHz' % freq
        datapoint=[freq]
        for sidebandfreq in sidebandfreqs:
            print '    sideband frequency: %g GHz' % sidebandfreq
            comp = yield sideband(anr,spec,fpga,corrector,freq,sidebandfreq)
            datapoint += [real(comp), imag(comp)]
        yield ds.add(datapoint)
        freq+=scanparams['sidebandCarrierStep']
    yield anr.output(False)
    yield spectDeInit(spec)
    yield cxn.microwave_switch.switch(0)
    returnValue(datasetNumber(dataset))
