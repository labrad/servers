package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

class CallSramDualBlockCommand(block1: String, block2: String, var delay: Double = -1) extends MemoryCommand {

  def getBlockName1(): String = {
    block1
  }

  def getBlockName2(): String = {
    block2
  }

  def getDelay(): Double = {
    require(delay > 0, "Dual-block SRAM delay not set!")
    delay
  }

  def setDelay(delay: Double): Unit = {
    this.delay = delay
  }

  def getBits(): Array[Long] = {
    // the GHz DACs server handles layout of SRAM for dual block
    Array[Long](0x800000, 0xA00000, 0xC00000)
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    // Call Sram memory command includes 3 memory commands plus the SRAM sequence
    require(delay > 0, "Dual-block SRAM delay not set!")
    val b1len = dac.getBlockLength(block1)
    val b2len = dac.getBlockLength(block2)
    dac.samplesToMicroseconds(b1len + b2len) + FpgaModelDac.clocksToMicroseconds(3) + this.delay / 1000.0
  }
}
