package org.labrad.qubits.config;


import org.labrad.data.Data;
import org.labrad.data.Request;

import com.google.common.base.Preconditions;

/**
 * This holds the configuration info for an ADC in demod mode.
 * 
 * It is held by an AdcChannel object. The global parameters are
 * start delay and filter function. The per-channel parameters are the
 * demod phase ((freq or steps/cycle) and (phase or offset steps))
 * and the trigger magnitude (sine amp and cosine amp, each a byte).
 * 
 * Note that this is a little different from the way that config objects
 * are normally done in this server. Normally the configs are for other servers
 * (e.g. microwave source) and are sent out as part of the GHz FPGA server's "setup packets".
 * Here the config is for a device on the GHz FPGA server and is sent as part of the main
 * run request.
 * 
 * TODO: AVERAGING MODE
 *   
 * @author pomalley
 *
 */
public class AdcDemodConfig extends AdcBaseConfig {

	/**
	 * maximum number of channels supported by the ADC
	 */
	static final int MAX_CHANNELS = 4;
	/**
	 * conversion from frequency to addresses per cycle
	 */
	static final double CYCLES_PER_HZ = 7629.0;
	/**
	 * conversion from phase to address offset
	 */
	static final double CYCLES_TO_PHI0 = 2^16;
	
	/**
	 * Each byte is the weight for a 4 ns interval.
	 * A single value can be repeated for a stretch in the middle.
	 * How long to repeat for is specified by stretchLen,
	 * and where to start repeating by stretchAt.
	 */
	String filterFunction;
	int stretchLen, stretchAt;
	
	/**
	 * Each channel has a dPhi, the number of addresses to step through
	 * per time sample.
	 */
	int dPhi[];
	
	/**
	 * phi0 is where on the sine lookup table to start (again for each channel)
	 */
	int phi0[];
	
	/**
	 * ampSin and ampCos are the magnitude of the cos and sin functions of a given channel
	 */
	int ampSin[], ampCos[];
	
	/**
	 * keeps a list of what channels we're using
	 */
	boolean inUse[];
	
	public AdcDemodConfig(String channelName) {
		super(channelName);
		startDelay = -1;
		filterFunction = "";
		stretchLen = -1; stretchAt = -1;
		
		dPhi = new int[MAX_CHANNELS]; for (int i : dPhi) i--;
		phi0 = new int[MAX_CHANNELS]; for (int i : phi0) i--;
		ampSin = new int[MAX_CHANNELS]; for (int i : ampSin) i--;
		ampCos = new int[MAX_CHANNELS]; for (int i : ampCos) i--;
		inUse = new boolean[MAX_CHANNELS];
	}
	
	/**
	 * @return array of booleans telling use state of each channel.
	 */
	public boolean[] getChannelUsage() {
		return inUse;
	}
	public void turnChannelOn(int channel) {
		Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
		inUse[channel] = true;
	}
	public void turnChannelOff(int channel) {
		Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
		inUse[channel] = false;
	}
	
	
	public void setFilterFunction(String filterFunction, int stretchLen, int stretchAt) {
		this.filterFunction = filterFunction;
		this.stretchLen = stretchLen;
		this.stretchAt = stretchAt;
	}
	
	public void setTrigMagnitude(int channel, int ampSin, int ampCos) {
		Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
		this.inUse[channel] = true;
		this.ampSin[channel] = ampSin;
		this.ampCos[channel] = ampCos;
	}
	
	/**
	 * sets the demodulation phase
	 * @param channel the channel index
	 * @param dPhi the number of addresses to step through per time step
	 * @param phi0 the initial offset
	 */
	public void setPhase(int channel, int dPhi, int phi0) {
		Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
		inUse[channel] = true;
		this.dPhi[channel] = dPhi;
		this.phi0[channel] = phi0;
	}

	/**
	 * sets the demodulation phase.
	 * @param channel the channel index
	 * @param frequency the frequency in Hz. it is converted in this function.
	 * @param phase the phase of the offset. it is converted to an address.
	 */
	public void setPhase(int channel, double frequency, double phase) {
		int dPhi = (int)Math.floor(frequency / CYCLES_PER_HZ);
		int phi0 = (int)(phase*(2^16));
		setPhase(channel, dPhi, phi0); 
	}
	
	/**
	 * In the demod case, the following packets are added:
	 * ADC Run Mode
	 * Start Delay
	 * ADC Filter Func
	 * for each channel:	ADC Demod Phase
	 * 						ADC Trig Magnitude
	 * @param runRequest The request to which we add the packets.
	 * @author pomalley
	 */
	public void addPackets(Request runRequest) {
		// check that the user has set everything that needs to be set
		Preconditions.checkState(startDelay > -1, "ADC Start Delay not set for channel '%s'", this.channelName);
		Preconditions.checkState(stretchLen > -1 && stretchAt > -1, "ADC Filter Func not set for channel '%s'", this.channelName);
		boolean oneFound = false;
		for (int i = 0; i < MAX_CHANNELS; i++) {
			if (inUse[i]) {
				oneFound = true;
				Preconditions.checkState(dPhi[i] > -1 && phi0[i] > -1, "ADC Demod phase not set on activated demod channel %s on channel '%s'", i, this.channelName);
				Preconditions.checkState(ampSin[i] > -1 && ampCos[i] > -1, "ADC Trig Magnitude not set on activated demod channel %s on channel '%s'", i, this.channelName);
			}
		}
		Preconditions.checkState(oneFound, "No demod channels activated for channel '%s'", this.channelName);
		// add the requests
		runRequest.add("ADC Run Mode", Data.valueOf("demodulate"));
		runRequest.add("Start Delay", Data.valueOf(this.startDelay));
		runRequest.add("ADC Filter Func", Data.valueOf(this.filterFunction),
				Data.valueOf(this.stretchLen), Data.valueOf(this.stretchAt));
		for (int i = 0; i < MAX_CHANNELS; i++) {
			if (inUse[i]) {
				runRequest.add("ADC Demod Phase", Data.valueOf(i), Data.valueOf(dPhi[i]), Data.valueOf(phi0[i]));
				runRequest.add("ADC Trig Magnitude", Data.valueOf(i), Data.valueOf(ampSin[i]), Data.valueOf(ampCos[i]));
			}
		}
	}
}
