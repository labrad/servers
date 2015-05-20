package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object StartTimerCommand extends MemoryCommand {
  def getBits(): Array[Long] = {
    Array[Long](0x400000)
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
