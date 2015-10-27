package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

class CallSramDualBlockCommand(val block1: String, val block2: String, private var _delay: Double = -1) extends MemoryCommand {

  def delay: Double = {
    require(delay > 0, "Dual-block SRAM delay not set!")
    delay
  }

  def setDelay(delay: Double): Unit = {
    _delay = delay
  }

  def cmdBits: Array[Long] = {
    // the GHz DACs server handles layout of SRAM for dual block
    Array[Long](0x800000, 0xA00000, 0xC00000)
  }

  def time_us(dac: FpgaModelDac): Double = {
    // Call Sram memory command includes 3 memory commands plus the SRAM sequence
    require(delay > 0, "Dual-block SRAM delay not set!")
    val b1len = dac.blockLength(block1)
    val b2len = dac.blockLength(block2)
    dac.samplesToMicroseconds(b1len + b2len) + FpgaModelDac.clocksToMicroseconds(3) + this.delay / 1000.0
  }
}
