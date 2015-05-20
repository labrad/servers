package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object EndSequenceCommand extends MemoryCommand {
  def getBits(): Array[Long] = {
    Array(0xF00000)
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
