package org.labrad.qubits.controller

import org.labrad.data.Data
import org.labrad.data.Request
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.jumptable.JumpTable

/**
 * Controller class for jump table boards.
 *
 * Essentially just a pass-through for addJumpTableEntry and addPackets.
 */
class JumpTableController(fpga: FpgaModelDac) extends FpgaController(fpga) {
  private val jumpTable = new JumpTable()

  override def hasDualBlockSram(): Boolean = {
    false
  }

  override def packets: Seq[(String, Data)] = {
    jumpTable.packets
  }

  //
  // Jump Table
  //
  def clear(): Unit = {
    jumpTable.clear()
  }

  def addJumpTableEntry(name: String, data: Data): Unit = {
    jumpTable.addEntry(name, data)
  }

  override def getSequenceLength_us(): Double = {
    sys.error("TODO: implement get sequence length for JT.")
  }

  override def getSequenceLengthPostSRAM_us(): Double = {
    sys.error("TODO: implement get sequence length for JT.")
  }
}
