package org.labrad.qubits.channeldata;

import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.channels.Deconvolvable;


public interface AnalogData extends Deconvolvable {
	public void setChannel(AnalogChannel channel);
	public int[] getDeconvolved();
	public void checkLength(int expected);
}
