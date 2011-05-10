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

	public int getStartDelay() {
		return startDelay;
	}

}