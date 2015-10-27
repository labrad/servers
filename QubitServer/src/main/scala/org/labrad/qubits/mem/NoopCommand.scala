package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object NoopCommand extends MemoryCommand {
  def cmdBits: Array[Long] = {
    Array[Long](0x000000)
  }

  def time_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
