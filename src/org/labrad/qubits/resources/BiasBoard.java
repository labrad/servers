package org.labrad.qubits.resources;

import org.labrad.qubits.enums.BiasFiberId;
import org.labrad.qubits.enums.DacFiberId;

public interface BiasBoard extends Resource {
	public void setDacBoard(BiasFiberId channel, DacBoard board, DacFiberId fiber);
}
