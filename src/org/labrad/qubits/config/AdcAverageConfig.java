package org.labrad.qubits.config;

import java.util.Map;

import org.labrad.data.Data;
import org.labrad.data.Request;

import com.google.common.base.Preconditions;

public class AdcAverageConfig extends AdcBaseConfig {
	
	public AdcAverageConfig(String name, Map<String, Long> buildProperties) {
		super(name, buildProperties);
		criticalPhase = 0;
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
		runRequest.add("Start Delay", Data.valueOf((long)this.startDelay));
		runRequest.add("ADC Filter Func", Data.valueOf("balhQLIYFGDSVF"), Data.valueOf(42L), Data.valueOf(42L));
	}
	
	double criticalPhase;
	public void setCriticalPhase(double criticalPhase) {
		Preconditions.checkState(criticalPhase >= 0.0 && criticalPhase <= 2*Math.PI,
				"Critical phase must be between 0 and 2PI");
		this.criticalPhase = criticalPhase;
	}
	@Override
	public boolean[][] interpretPhases(long[] Is, long[] Qs) {
		Preconditions.checkArgument(Is.length == Qs.length, "Is and Qs must have same length!");
		boolean[][] switches = new boolean[0][Is.length];
		for (int i = 0; i < Is.length; i++)
			switches[0][i] = Math.atan2(Is[i], Qs[i]) < criticalPhase;
		return switches;
	}

}
