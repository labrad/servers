package org.labrad.qubits.resources;

import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.enums.DacFiberId;

public interface BiasBoard extends Resource {
	public void setDacBoard(DcRackFiberId channel, DacBoard board, DacFiberId fiber);
}
