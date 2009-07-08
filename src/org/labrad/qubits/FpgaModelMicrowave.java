package org.labrad.qubits;

import java.util.Arrays;

import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.resources.DacBoard;

public class FpgaModelMicrowave extends FpgaModelBase {
	
	private IqChannel iq = null;

	public FpgaModelMicrowave(DacBoard dacBoard, Experiment expt) {
		super(dacBoard, expt);
	}
	
	public void setIqChannel(IqChannel iq) {
		this.iq = iq;
	}
	
	@Override
	protected boolean hasDacChannels() {
		return (iq != null);
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
		if (iq != null) {
			int[] A = iq.getSramDataA(block);
			int[] B = iq.getSramDataB(block);
			for (int i = 0; i < A.length; i++) {
				sram[i] |= ((long)(A[i] & 0x3FFF)) + ((long)((B[i] & 0x3FFF) << 14));
			}
		}
		return sram;
	}
}
