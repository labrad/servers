package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object EndSequenceCommand extends MemoryCommand {
  def cmdBits: Array[Long] = {
    Array(0xF00000)
  }

  def time_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
