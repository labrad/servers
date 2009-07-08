package org.labrad.qubits.mem;

public class CallSramDualBlockCommand implements MemoryCommand {
	private String block1, block2;
	private double delay;
	
	public CallSramDualBlockCommand(String block1, String block2, double delay) {
		this.block1 = block1;
		this.block2 = block2;
		this.delay = delay;
	}
	
	public String getBlockName1() {
		return block1;
	}
	
	public String getBlockName2() {
		return block2;
	}
	
	public double getDelay() {
		return delay;
	}
	
	public long[] getBits() {
		// the GHz DACs server handles layout of SRAM for dual block
		return new long[] {0x800000,
                	   	   0xA00000,
                		   0xC00000};
	}

}
