package org.labrad.qubits.controller

import org.labrad.data.Request
import org.labrad.qubits.FpgaModelDac

/**
 * The FpgaController represents the controlling architecture of a DAC board.
 * Currently, there are two types: {@link MemoryController} and {@link JumpTableController}.
 */
abstract class FpgaController(protected val fpga: FpgaModelDac) {

  def getSequenceLength_us(): Double
  def getSequenceLengthPostSRAM_us(): Double

  def hasDualBlockSram(): Boolean

  def addPackets(runRequest: Request): Unit

  def clear(): Unit
}
