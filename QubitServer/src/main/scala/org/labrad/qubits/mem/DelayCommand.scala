package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

class DelayCommand(var cycles: Int) extends MemoryCommand {

  def setDelay(cycles: Int): Unit = {
    this.cycles = cycles
  }

  def getDelay(): Int = {
    this.cycles
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(this.cycles)
  }

  def getBits(): Array[Long] = {
    var left = cycles
    val arr = Array.newBuilder[Long]
    while (left > 0x0FFFFF) {
      arr += 0x3FFFFF
      left -= 0x0FFFFF
    }
    arr += (0x300000 + left)
    arr.result()
  }
}
