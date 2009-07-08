package org.labrad.qubits.channels;


public interface SramChannel extends Channel {
	public void startBlock(String name, long length);
}
