package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object StopTimerCommand extends MemoryCommand {
  def cmdBits: Array[Long] = {
    Array[Long](0x400001)
  }

  def time_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
