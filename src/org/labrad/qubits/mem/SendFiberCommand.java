package org.labrad.qubits.mem;

public class SendFiberCommand implements MemoryCommand {
	private int channel;
	private int bits;
	
	public SendFiberCommand(int channel, int bits) {
		this.channel = channel;
		this.bits = bits;
	}
	
	public long[] getBits() {
		int send;
		switch (channel) {
			case 0: send = 0x100000; break;
			case 1: send = 0x200000; break;
			default:
				throw new RuntimeException("No channel.");
		}
		return new long[] {send + (bits & 0x0FFFFF)};
	}
}
