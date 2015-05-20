package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac

class CallSramCommand(blockName: String) extends MemoryCommand {
  private var startAddr: Int = 0
  private var endAddr: Int = 0

  def getBlockName(): String = {
    blockName
  }

  def setStartAddress(startAddr: Int): Unit = {
    this.startAddr = startAddr
  }

  def setEndAddress(endAddr: Int): Unit = {
    this.endAddr = endAddr
  }

  def getBits(): Array[Long] = {
    Array[Long](0x800000 + (startAddr & 0x0FFFFF),
                0xA00000 + (endAddr & 0x0FFFFF),
                0xC00000)
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    // Call Sram memory command includes 3 memory commands plus the SRAM sequence
    dac.samplesToMicroseconds(endAddr - startAddr) + FpgaModelDac.clocksToMicroseconds(3)
  }
}
