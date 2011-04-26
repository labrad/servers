package org.labrad.qubits.config;

import org.labrad.data.Data;
import org.labrad.data.Request;

import com.google.common.base.Preconditions;

public class AdcAverageConfig extends AdcBaseConfig {
	
	public AdcAverageConfig(String name) {
		super(name);
	}

	/**
	 * in the Average mode, the following packets are added:
	 * ADC Run Mode
	 * Start Delay
	 * ... and that's it.
	 * @param runRequest The request to which we add the packets.
	 * @author pomalley
	 */
	@Override
	public void addPackets(Request runRequest) {
		Preconditions.checkState(startDelay > -1, "ADC Start Delay not set for channel '%s'", this.channelName);
		runRequest.add("ADC Run Mode", Data.valueOf("average"));
		runRequest.add("Start Delay", Data.valueOf(this.startDelay));
	}

}
