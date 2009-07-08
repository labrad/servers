package org.labrad.qubits.mem;

public class StartTimerCommand implements MemoryCommand {
	private StartTimerCommand() {}
	
	private static final StartTimerCommand INSTANCE = new StartTimerCommand();
	
	public static StartTimerCommand getInstance() {
		return INSTANCE;
	}
	
	public long[] getBits() {
		return new long[] {0x400000};
	}
}
