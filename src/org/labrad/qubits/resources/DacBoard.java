package org.labrad.qubits.resources;

import java.util.Map;

import org.labrad.qubits.enums.BiasFiberId;
import org.labrad.qubits.enums.DacFiberId;

import com.google.common.collect.Maps;

public abstract class DacBoard implements Resource {
	private String name;
	
	private Map<DacFiberId, BiasBoard> fibers = Maps.newHashMap();
	private Map<DacFiberId, BiasFiberId> fiberChannels = Maps.newHashMap();
	
	public DacBoard(String name) {
		this.name = name;
	}
	
	public String getName() {
		return name;
	}
	
	public void setFiber(DacFiberId fiber, BiasBoard board, BiasFiberId channel) {
		fibers.put(fiber, board);
		fiberChannels.put(fiber, channel);
	}
}
