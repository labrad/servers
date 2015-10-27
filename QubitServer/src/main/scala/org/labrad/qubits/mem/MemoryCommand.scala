package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

trait MemoryCommand {
  def cmdBits: Array[Long]
  def time_us(dac: FpgaModelDac): Double
}
