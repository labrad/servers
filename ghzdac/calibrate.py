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

# This module contains the calibration scripts. They must not require any
# user interaction because they are used not only for the initial
# recalibration but also for recalibration. The user interface is provided
# by GHz_DAC_calibrate in the "scripts" package. Eventually async versions
# will be provide for use in a LABRAD server

from ghzdac import SESSIONNAME, ZERONAME, PULSENAME, CHANNELNAMES, \
     IQNAME, SETUPTYPESTRINGS, IQcorrector
from numpy import exp, pi, arange, real, imag, min, max, log, transpose, alen
from labrad.types import Value
from datetime import datetime
#trigger to be set:
#0x1: trigger S0
#0x2: trigger S1
#0x4: trigger S2
#0x8: trigger S3
#e.g. 0xA sets trigger S1 and S3
trigger = 0xFL << 28

DACMAX= 1 << 13 - 1
DACMIN= 1 << 13


def spect_init(spec):
    spec.gpib_write(':POW:RF:ATT 0dB\n:AVER:STAT OFF\n:BAND 300Hz\n:FREQ:SPAN 100Hz\n:INIT:CONT OFF\n')

def spect_freq(spec,freq):
    spec.gpib_write(':FREQ:CENT %gGHz\n' % freq)

def signalpower(spec):
    """returns the mean power in mW read by the spectrum analyzer"""
    return 10.0**(0.1*float(spec.gpib_query('*TRG\n*OPC?\n:TRAC:MATH:MEAN? TRACE1\n')[2:]))


def makesample(a,b):
    """computes sram sample from dac A and B values"""
    if (max(a) > 0x1FFF) or (max(b) > 0x1FFF) or (min(a) < -0x2000) or (min(b) < -0x2000):
        print 'DAC overflow'
    return long(a & 0x3FFFL) | (long(b & 0x3FFFL) << 14)


def continuouspower(spec,fpga,a,b):
    """returns signal power from the spectrum analyzer"""
    dac=[makesample(a,b)]*64
    dac[0] |= trigger
    fpga.run_sram(dac,True)
    return signalpower(spec)



def minpos(l,c,r):
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

def zero(anr, spec, fpga, freq):
    """Calibrates the zeros for DAC A and B using the spectrum analyzer"""
   
    anr.frequency(Value(freq,'GHz'))
 
  
    spect_freq(spec,freq)
    a=0
    b=0
    precision=0x800
    print '    calibrating at %g GHz...' % freq
    while precision > 0:
        al=continuouspower(spec,fpga,a-precision,b)
        ar=continuouspower(spec,fpga,a+precision,b)
        ac =continuouspower(spec,fpga,a,b)
        corra=long(round(precision*minpos(al,ac,ar)))
        a+=corra

        bl=continuouspower(spec,fpga,a,b-precision)
        br=continuouspower(spec,fpga,a,b+precision)
        bc =continuouspower(spec,fpga,a,b)
        corrb=long(round(precision*minpos(bl,bc,br)))
        b+=corrb
        optprec=2*max([abs(corra),abs(corrb)]) 
        precision/=2
        if precision>optprec:
            precision=optprec
        print '        a = %4d  b = %4d uncertainty : %4d, power %6.1f dBm' % \
              (a, b, precision, 10 * log(bc) / log(10.0))
    return [a,b]


def zeroscancarrier(cxn, scanparams, boardname):
    """Measures the DAC zeros in function of the carrier frequency."""
    fpga = cxn.ghz_dacs
    anr = cxn.anritsu_server
    spec = cxn.spectrum_analyzer_server
    scope = cxn.sampling_scope

    anr.amplitude(Value(scanparams['anritsu dBm'],'dBm'))
    anr.output(True)

    print 'Zero calibration from %g GHz to %g GHz in steps of %g GHz...' % \
        (scanparams['carrierMin'],scanparams['carrierMax'],scanparams['carrierStep'])

    ds = cxn.data_vault
    ds.cd(['',SESSIONNAME,boardname],True)
    ds.new(ZERONAME,[('Frequency','GHz')],[('DAC zero', 'A', 'clics'),
                                           ('DAC zero', 'B', 'clics')])
    ds.add_parameter('Anritsu amplitude',
                     Value(scanparams['anritsu dBm'],'dBm'))

    freq=scanparams['carrierMin']
    while freq<scanparams['carrierMax']:
        ds.add([freq]+zero(anr,spec,fpga,freq))
        freq+=scanparams['carrierStep']


####################################################################
# Pulse calibration                                                #
####################################################################

def measure_impulse_response(fpga, scope, baseline, pulse, dacoffsettime=6):
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

    triggerdelay=30
    looplength=256
    pulseindex=(triggerdelay-dacoffsettime) % looplength
    scope.start_time(Value(triggerdelay,'ns'))
    #calculate the baseline voltage by capturing a trace without a pulse

    data = looplength * [baseline]
    data[0] |= trigger
    fpga.run_sram(data,True)

    data[pulseindex] = pulse | (trigger * (pulseindex == 0))
    fpga.run_sram(data,True)
    data=scope.get_trace(1).asarray
    data[0]-=triggerdelay*1e-9
    return data


def modulated_pulse(cxn, scanparams, boardname, setupType, baselineA, baselineB):
    """Measures the impulse response of the DACs after the IQ mixer"""
    pulseheight=0x1800

    anr = cxn.anritsu_server
    anr.frequency(Value(scanparams['carrier'],'GHz'))
    anr.amplitude(Value(scanparams['anritsu dBm'],'dBm'))
    anr.output(True)
    
    fpga = cxn.ghz_dacs
 
    #Set up the scope
    scope = cxn.sampling_scope
    scope.reset()
    scope.channel(1)
    scope.trace(1)
    scope.record_length(5120)
    scope.average(128)
    scope.sensitivity(Value(10.0,'mV'))
    scope.offset(Value(0,'mV'))
    scope.time_step(Value(2,'ns'))
    scope.trigger_level(Value(0.18,'V'))
    scope.trigger_positive()

    baseline = makesample(baselineA,baselineB)
    print "Measuring offset voltage..."
    offset = measure_impulse_response(fpga, scope, baseline, baseline)[2:]
    offset = sum(offset) / len(offset)

    print "Measuring pulse response DAC A..."
    traceA = measure_impulse_response(fpga, scope, baseline,
        makesample(baselineA+pulseheight,baselineB),
        dacoffsettime=scanparams['dacOffsetTimeIQ'])

    print "Measuring pulse response DAC B..."
    traceB = measure_impulse_response(fpga, scope, baseline,
        makesample(baselineA,baselineB+pulseheight),
        dacoffsettime=scanparams['dacOffsetTimeIQ'])

    starttime = traceA[0]
    timestep = traceA[1]
    if (starttime != traceB[0]) or (timestep != traceB[1]) :
        print """Time scales are different for measurement of DAC A and B.
        Did you change settings on the scope during the measurement?"""
        exit
    #set output to zero    
    fpga.run_sram([baseline]*4)
    ds = cxn.data_vault
    ds.cd(['',SESSIONNAME,boardname],True)
    ds.new(PULSENAME,[('Time','ns')],[('Voltage','A','V'),('Voltage','B','V')])
    ds.add_parameter('Setup type', SETUPTYPESTRINGS[setupType])
    ds.add_parameter('Anritsu frequency',
                     Value(scanparams['carrier'],'GHz'))
    ds.add_parameter('Anritsu amplitude',
                     Value(scanparams['anritsu dBm'],'dBm'))
    ds.add_parameter('DAC offset time',Value(scanparams['dacOffsetTimeIQ'],'ns'))
    
    ds.add(transpose([1e9*(starttime+timestep*arange(alen(traceA)-2)),
        traceA[2:]-offset,
        traceB[2:]-offset]))


def unmodulated_pulse(cxn,scanparams,boardname,channel):
    fpga = cxn.ghz_dacs

    baseline = -0x2000
    pulseheight=0x3FFF
    if channel:
        pulse = makesample(baseline,baseline+pulseheight)
    else:
        pulse = makesample(baseline+pulseheight,baseline)
    baseline = makesample(baseline,baseline)
    #Set up the scope
    scope = cxn.sampling_scope
    scope.reset()
    scope.channel(1)
    scope.trace(1)
    scope.record_length(5120)
    scope.average(128)
    scope.sensitivity(Value(100.0,'mV'))
    scope.offset(Value(0,'mV'))
    scope.time_step(Value(2,'ns'))
    scope.trigger_level(Value(0.18,'V'))
    scope.trigger_positive()
        
    print 'Measuring offset voltage...'
    offset = measure_impulse_response(fpga, scope, baseline, baseline,
        dacoffsettime=scanparams['dacOffsetTimeNoIQ'])[2:]
    offset = sum(offset) / len(offset)

    print 'Measuring pulse response...'
    trace = measure_impulse_response(fpga, scope, baseline, pulse,
        dacoffsettime=scanparams['dacOffsetTimeNoIQ'])

    fpga.run_sram([0]*4,False)
    ds = cxn.data_vault
    ds.cd(['',SESSIONNAME,boardname],True)
    ds.new(CHANNELNAMES[channel],[('Time','ns')],[('Voltage','','V')])
    ds.add_parameter('DAC offset time',Value(scanparams['dacOffsetTimeNoIQ'],'ns'))
    ds.add(transpose([1e9*(trace[0]+trace[1]*arange(alen(trace)-2)),
        trace[2:]-offset]))


####################################################################
# Sideband calibration                                             #
####################################################################

def sidebandsignal(spec,fpga,corrector,carrierfreq,sidebandfreq,compensation):
    """Puts out a signal at carrierfreq+sidebandfreq and return the power at
    returns the power at carrierfreq-sidebandfreq"""

    arg=-2.0j*pi*sidebandfreq*arange(1000.0)
    signal=corrector.DACify(carrierfreq, 0.5 * exp(arg) + 0.5 * compensation * exp(-arg), \
                            loop=True, iqcor=False, rescale=True)
    signal[0] = signal[0] | (0x8<<28)
    fpga.run_sram(signal,True)
    return signalpower(spec) / corrector.last_rescale_factor

 
def zerosideband(anr,spect,fpga,corrector,carrierfreq,sidebandfreq):
    if abs(sidebandfreq) < 3e-5:
        return 0.0j
    anr.frequency(Value(carrierfreq,'GHz'))
    comp=0.0j
    precision=1.0
    spect_freq(spect,carrierfreq-sidebandfreq)
    while precision > 2.0**-14:
        lR = sidebandsignal(spect, fpga, corrector, carrierfreq, sidebandfreq, comp - precision)
        rR = sidebandsignal(spect, fpga, corrector, carrierfreq, sidebandfreq, comp + precision)
        cR  = sidebandsignal(spect, fpga, corrector, carrierfreq, sidebandfreq, comp)
        
        corrR = precision * minpos(lR,cR,rR)
        comp += corrR
        lI = sidebandsignal(spect, fpga, corrector, carrierfreq, sidebandfreq, comp - 1.0j * precision)
        rI = sidebandsignal(spect, fpga, corrector, carrierfreq, sidebandfreq, comp + 1.0j * precision)
        cI  = sidebandsignal(spect, fpga, corrector, carrierfreq, sidebandfreq, comp)
        
        corrI = precision * minpos(lI,cI,rI)
        comp += 1.0j * corrI
        precision=min([2.0 * max([abs(corrR),abs(corrI)]), precision / 2.0])
        print '      compensation: %.4f%+.4fj +- %.4f, opposite sb: %6.1f dBm' % \
            (real(comp), imag(comp), precision, 10.0 * log(cI) / log(10.0))
    return comp


def sideband_scan_carrier(cxn, scanparams, boardname, corrector):
    """Determines relative I and Q amplitudes by canceling the undesired
       sideband at different sideband frequencies."""

    fpga=cxn.ghz_dacs
    anr=cxn.anritsu_server
    spec=cxn.spectrum_analyzer_server
    scope=cxn.sampling_scope
    ds=cxn.data_vault

    anr.amplitude(Value(scanparams['anritsu dBm'],'dBm'))
    anr.output(True)



    print 'Sideband calibration from %g GHz to %g GHz in steps of %g GHz...' \
       %  (scanparams['carrierMin'],scanparams['carrierMax'],scanparams['sidebandCarrierStep'])
    
    sidebandfreqs = scanparams['sidebandFreqStep'] * arange(0.5 * (1 - scanparams['sidebandFreqCount']), 
                                              0.5 * (1 + scanparams['sidebandFreqCount']))
    dependents = []
    for sidebandfreq in sidebandfreqs:
        dependents += [('relative compensation', 'Q at f_SB = %g MHz' % (sidebandfreq*1e3),''),
                       ('relative compensation', 'I at f_SB = %g MHz' % (sidebandfreq*1e3),'')]    
    ds.cd(['',SESSIONNAME,boardname],True)
    ds.new(IQNAME,[('Antritsu Frequency','GHz')],dependents)
    ds.add_parameter('Anritsu amplitude',
                     Value(scanparams['anritsu dBm'],'dBm'))
    ds.add_parameter('Sideband frequency step',
                     Value(scanparams['sidebandFreqStep']*1e3,'MHz'))
    ds.add_parameter('Number of sideband frequencies',
                     scanparams['sidebandFreqCount'])

    freq=scanparams['carrierMin']
    while freq<scanparams['carrierMax']:
        print '  carrier frequency: %g GHz' % freq
        datapoint=[freq]
        for sidebandfreq in sidebandfreqs:
            print '    sideband frequency: %g GHz' % sidebandfreq
            comp = zerosideband(anr,spec,fpga,corrector,freq,sidebandfreq)
            datapoint += [real(comp), imag(comp)]
        ds.add(datapoint)
        freq+=scanparams['sidebandCarrierStep']

