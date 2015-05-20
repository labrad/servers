package org.labrad.qubits.controller;

import org.labrad.data.Request;
import org.labrad.qubits.FpgaModelDac;

/**
 * The FpgaController represents the controlling architecture of a DAC board.
 * Currently, there are two types: {@link MemoryController} and {@link JumpTableController}.
 */
public abstract class FpgaController {
  protected FpgaModelDac fpga;

  public abstract double getSequenceLength_us();
  public abstract double getSequenceLengthPostSRAM_us();

  public FpgaController(FpgaModelDac fpga) {
    this.fpga = fpga;
  }

  public abstract boolean hasDualBlockSram();

  public abstract void addPackets(Request runRequest);

  public abstract void clear();
}
