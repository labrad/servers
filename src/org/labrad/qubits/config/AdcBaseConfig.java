package org.labrad.qubits.config;

import java.util.Map;

import org.labrad.data.Request;

public abstract class AdcBaseConfig {
	
	protected final Map<String, Long> buildProperties;

	/**
	 * number of clock cycles to delay
	 */
	protected int startDelay;
	
	/**
	 * name of the channel we belong to
	 */
	protected final String channelName;
	
	public AdcBaseConfig(String channelName, Map<String, Long> buildProperties) {
		this.channelName = channelName;
		this.buildProperties = buildProperties;
	}

	public void setStartDelay(int startDelay) {
		this.startDelay = startDelay;
	}

	/**
	 * Adds packets to a labrad request to the fpga server.
	 * These packets configure the ADC. The ADC must already have been
	 * selected in this request. 
	 * @param runRequest The request to which we add the packets.
	 * @author pomalley
	 */
	public abstract void addPackets(Request runRequest);
	
	/**
	 * Converts Is and Qs to T/F based on the previously given critical phase.
	 * For Average mode there is one critical phase, and we just loop through all of them and do
	 * switched = (atan2(i, q) < criticalPhase)
	 * (we then wrap it in a length-1 array to match with demod mode)
	 * For demod mode we interpret the input arrays to be of length numChannels*numRuns and of format:
	 * [channel1-run1-i, channel2-run1-i, ..., channelN-run1-i, channel1-run2-i, ..., ..., channelN-runN-i]
	 * The return is broken out by channel and by run; switches[channelNumber][runNumber].
	 * @param Is
	 * @param Qs
	 * @return
	 */
	public abstract boolean[][] interpretPhases(long[] Is, long[] Qs);

	public int getStartDelay() {
		return startDelay;
	}

}