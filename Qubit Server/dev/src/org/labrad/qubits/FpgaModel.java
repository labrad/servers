package org.labrad.qubits;

import org.labrad.qubits.resources.DacBoard;

public interface FpgaModel {

  public String getName();
  public DacBoard getDacBoard();
  public double getSequenceLength_us();
  public double getSequenceLengthPostSRAM_us();
}
