package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

object StopTimerCommand extends MemoryCommand {
  def getBits(): Array[Long] = {
    Array[Long](0x400001)
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
