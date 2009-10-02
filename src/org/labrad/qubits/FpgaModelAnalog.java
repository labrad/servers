package org.labrad.qubits;

import java.util.Arrays;
import java.util.Map;

import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.enums.DacAnalogId;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.collect.Maps;

public class FpgaModelAnalog extends FpgaModelBase {
	
	private Map<DacAnalogId, AnalogChannel> dacs = Maps.newEnumMap(DacAnalogId.class);
	
	public FpgaModelAnalog(DacBoard dacBoard, Experiment expt) {
		super(dacBoard, expt);
	}
	
	public void setAnalogChannel(DacAnalogId id, AnalogChannel ch) {
		dacs.put(id, ch);
	}
	
	@Override
	protected boolean hasDacChannels() {
		return !dacs.isEmpty();
	}
	
	public AnalogChannel getDacChannel(DacAnalogId id) {
		return dacs.get(id);
	}
	
	/**
	 * Get sram bits for a particular block
	 * @param block
	 * @return
	 */
	@Override
	protected long[] getSramDacBits(String block) {
		final long[] sram = new long[expt.getBlockLength(block)];
		Arrays.fill(sram, 0);
		for (DacAnalogId id : dacs.keySet()) {
			int[] vals = dacs.get(id).getSramData(block);
			for (int i = 0; i < vals.length; i++) {
				sram[i] |= (long)((vals[i] & 0x3FFF) << id.getShift());
			}
		}
		return sram;
	}
}
