package org.labrad.qubits.resources;

import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;

public interface BiasBoard extends Resource {
  public void setDacBoard(DcRackFiberId channel, DacBoard board, DacFiberId fiber);
}
