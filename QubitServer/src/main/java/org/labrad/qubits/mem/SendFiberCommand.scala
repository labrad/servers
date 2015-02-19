package org.labrad.qubits.mem

import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.enums.DacFiberId

case class SendFiberCommand(channel: DacFiberId, bits: Int) extends MemoryCommand {

  def getBits(): Array[Long] = {
    val send = channel match {
      case DacFiberId.FOUT_0 => 0x100000
      case DacFiberId.FOUT_1 => 0x200000
      case DacFiberId.FIN => sys.error(s"Invalid DAC fiber id: $channel")
    }
    Array[Long](send + (bits & 0x0FFFFF))
  }

  def getTime_us(dac: FpgaModelDac): Double = {
    FpgaModelDac.clocksToMicroseconds(1)
  }
}
