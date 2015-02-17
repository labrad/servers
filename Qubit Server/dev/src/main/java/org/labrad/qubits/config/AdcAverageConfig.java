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
	public boolean[] interpretPhases(int[] Is, int[] Qs, int channel) {
		Preconditions.checkArgument(Is.length == Qs.length, "Is and Qs must have same length!");
		if (channel != -1) {
			System.err.println("WARNING: interpretPhases for average mode ADC called with demod channel != -1");
		}
		boolean[] switches = new boolean[Is.length];
		for (int i = 0; i < Is.length; i++)
			switches[i] = Math.atan2(Is[i], Qs[i]) < criticalPhase;
		return switches;
	}

}
