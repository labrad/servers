package org.labrad.qubits.controller;

import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.jumptable.JumpTable;

/**
 * Runs da jump table.
 */
public class JumpTableController extends FpgaController {
  private final JumpTable jumpTable = new JumpTable();

  public JumpTableController(FpgaModelDac fpga) {
    super(fpga);
    clear();
  }

  @Override
  public boolean hasDualBlockSram() {
    return false;
  }

  @Override
  public void addPackets(Request runRequest) {
    jumpTable.addPackets(runRequest);
  }

  //
  // Jump Table
  //
  public void clear() {
    jumpTable.clear();
  }
  public void addJumpTableEntry(String name, Data data) {
    jumpTable.addEntry(name, data);
  }

  public JumpTable getJumpTable() {
    return jumpTable;
  }

  @Override
  public double getSequenceLength_us() {
    throw new RuntimeException("TODO: implement get sequence length for JT.");
  }

  @Override
  public double getSequenceLengthPostSRAM_us() {
    throw new RuntimeException("TODO: implement get sequence length for JT.");
  }
}
