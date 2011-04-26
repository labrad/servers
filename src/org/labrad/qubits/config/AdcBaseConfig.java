package org.labrad.qubits.config;

import org.labrad.data.Request;

public abstract class AdcBaseConfig {

	/**
	 * number of clock cycles to delay
	 */
	protected int startDelay;
	
	/**
	 * name of the channel we belong to
	 */
	protected String channelName;
	
	public AdcBaseConfig(String channelName) {
		this.channelName = channelName;
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

}