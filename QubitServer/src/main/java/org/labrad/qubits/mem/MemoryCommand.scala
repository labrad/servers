package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

trait MemoryCommand {
  def getBits(): Array[Long]
  def getTime_us(dac: FpgaModelDac): Double
}
