#(count, delay, length, rchan)

idx = idx+1
plt.close('all')
cxn.manager.expire_context()
cxn.ghz_fpgas.select_device(1)
cxn.ghz_fpgas.adc_monitor_outputs('start', 'demod0I[b0]')
mix_wfm = np.exp(2*np.pi*1j*np.arange(512) * 2.0 * .0150)
mixTable = np.array(np.column_stack((np.real(mix_wfm*127), np.imag(mix_wfm*127))), dtype=int)
#mixTable = mixTable*0
#mixTable[0,0] = idx
plt.plot(mixTable[:,0])
plt.plot(mixTable[:,1])
triggerTable = [(1, 10, 100, 1)]
cxn.ghz_fpgas.select_device(1)
cxn.ghz_fpgas.adc_trigger_table(triggerTable)
for jj in range(12):
    cxn.ghz_fpgas.adc_mixer_table(jj, mixTable)
#cxn.ghz_fpgas.adc_mixer_table(0, mixTable)
data = cxn.ghz_fpgas.adc_run_demod()
data

plt.close('all')
cxn.ghz_fpgas.adc_recalibrate()
I, Q = cxn.ghz_fpgas.adc_run_average()
plt.plot(I)


x = []
fs = np.linspace(-0.02,0.02,41)
for f in fs:
    cxn.manager.expire_context()
    cxn.ghz_fpgas.select_device(1)
    cxn.ghz_fpgas.adc_monitor_outputs('start', 'don')
    mix_wfm = np.exp(2*np.pi*1j*np.arange(512) * 2.0 * f)
    #mix_wfm = np.exp(2*np.pi*1j*np.arange(512) * 2.0 * .000)*np.exp(-1j*np.pi/4)
    mixTable = np.array(np.column_stack((np.real(mix_wfm*127), np.imag(mix_wfm*127))), dtype=int)
    triggerTable = [(1, 10, 100, 1)]
    cxn.ghz_fpgas.select_device(1)
    cxn.ghz_fpgas.adc_trigger_table(triggerTable)
    cxn.ghz_fpgas.adc_mixer_table(0, mixTable)
    #cxn.ghz_fpgas.adc_mixer_table(0, mixTable)
    data = cxn.ghz_fpgas.adc_run_demod()
    x.append(data[0][0][0][0])
    
plt.plot(fs,x)

cxn.manager.expire_context()
cxn.ghz_fpgas.select_device(1)
cxn.ghz_fpgas.adc_monitor_outputs('ADdone', 'alldone')
#mixTable *= 0
#mixTable[3,:] = 127
#            rcount rdelay rlen, rchan
triggerTable = [(3, 10, 250, 12)]
cxn.ghz_fpgas.select_device(1)
cxn.ghz_fpgas.adc_trigger_table(triggerTable)
for idx in range(12):
    mix_wfm = np.exp(2*np.pi*1j*np.arange(512) * 2.0 * .010)#*np.exp(-1j*np.pi*idx/3)
    mixTable = np.array(np.column_stack((np.real(mix_wfm*127), np.imag(mix_wfm*127))), dtype=int)    
    cxn.ghz_fpgas.adc_mixer_table(idx, mixTable)
#cxn.ghz_fpgas.adc_mixer_table(0, mixTable)
data = cxn.ghz_fpgas.adc_run_demod()
print np.array(data[0])

def flatMix(mon0='start',mon1='don',triggerTable = [(1,1250,100,1)]):#trigger=1,chan=1):
    cxn.manager.expire_context()
    cxn.ghz_fpgas.select_device(1)
    cxn.ghz_fpgas.adc_monitor_outputs(mon0, mon1)
    #mixTable *= 0
    #mixTable[3,:] = 127
    #            rcount rdelay rlen, rchan
    #triggerTable = [(trigger, 1250, 100, chan)]
    cxn.ghz_fpgas.select_device(1)
    cxn.ghz_fpgas.adc_trigger_table(triggerTable)
    for idx in range(12):
        mix_wfm = np.exp(2*np.pi*1j*np.arange(512) * 2.0 * .010)*np.exp(-1j*np.pi*idx/np.e)
        mixTable = np.array(np.column_stack((np.real(mix_wfm*127), np.imag(mix_wfm*127))), dtype=int)    
        cxn.ghz_fpgas.adc_mixer_table(idx, mixTable)
    #cxn.ghz_fpgas.adc_mixer_table(0, mixTable)
    data = cxn.ghz_fpgas.adc_run_demod()

    IQdata = np.array(data[0][0])
    Z = IQdata[:,0] + 1j*IQdata[:,1]
    print "absolute value: ", np.abs(Z)
    print "angle: ", np.angle(Z)*180/np.pi, " degrees"
    return Z
    
data = []
for idx in range(512):
    mixerTable = fpgaTest.deltaMixerTable(idx)
    currData = fpgaTest.mixerTriggerTable(s, cxn, mixerTable = mixerTable, demodFreq=None)
    data.append(currData[0][0][0])
    
"""
List of experiments to check ADC:
1. Check that multiple channels works as expected
2. Check that multiple demodulation works as expected
3. Check multiple channels + multiple demods works as expected
--> Get right number of packets/data entries: check

13. multiple triggerTable rows
--> Right number of packets/data entries
12. multiple channels w/ same mixer table give same value
--> Check
10. exactly multiple of 11 readouts, dont get extra empty packet
--> Check

8. Check minimum rdelay (minimum start-start and minimum stop-start)
--> Packet count correct for rdelay, rlen = (1, 1)
### BUT: data gets screwed up for rdelay < 50 cycles and 12 channels

4. Check that the phase is consistent for multiple demods -> demod multiple times for a signal at some frequency and see that the phase shift makes sense between demods, given the rdelay

--> This works.  There was a one clock cycle error in the documentation, rdelay[15..0] +4 = delay cycles
        Recheck after verifying rlen below

9. How does minimum rdelay vary with rchan:  
        appears to work with rdelay = 1 rlen=2

5. Check that phase locked source gives same demod value for each experiment repetition
--> Check
7. Check daisy chain & sequence_run
--> Check
14. 1 us start multiple in daisy chain mode
--> Check

5a. Make sure all demods (esp. 0, 12) run the same time steps
--> Check
6. Compare average mode to demod mode by reconstructing a signal using many delta functions for demod mode (needs phase locked source).
--> Check
15. Check that the rlen is not off by 1
--> Check

11. check various conditions that may put the board in a weird state
"""
