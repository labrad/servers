package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object NoopCommand extends MemoryCommand {
  def getBits(): Array[Long] = {
    Array[Long](0x000000)
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
