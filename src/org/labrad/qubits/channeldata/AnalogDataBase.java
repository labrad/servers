package org.labrad.qubits.channeldata;

import org.labrad.qubits.channels.AnalogChannel;

public abstract class AnalogDataBase implements AnalogData {

	private AnalogChannel channel;
	
	private boolean isDeconvolved = false;
	
	@Override
	public void setChannel(AnalogChannel channel) {
		this.channel = channel;
	}
	
	protected AnalogChannel getChannel() {
		return channel;
	}
	
	/**
	 * Whether this bit of analog data has been deconvolved.
	 */
	@Override
	public boolean isDeconvolved() {
		return isDeconvolved;
	}
	
	protected void setDeconvolved(boolean isDeconvolved) {
		this.isDeconvolved = isDeconvolved;
	}
}
