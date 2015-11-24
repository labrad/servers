package org.labrad.qubits.mem

import org.labrad.qubits.channels.FastBiasChannel
import org.labrad.qubits.enums.BiasCommandType
import org.labrad.qubits.enums.BiasCommandType._

object FastBiasCommands {
  def get(cmdType: BiasCommandType, fb: FastBiasChannel, v: Double): SendFiberCommand = {
    val gain = fb.getFastBias().getGain(fb.getDcFiberId())
    val vSend = v / gain
    cmdType match {
      case DAC0 => setDac0(fb, vSend)
      case DAC0_NOSELECT => setDac0NoSelect(fb, vSend)
      case DAC1 => setDac1Fast(fb, vSend)
      case DAC1_SLOW => setDac1Slow(fb, vSend)
    }
  }

  private def setDac0(fb: FastBiasChannel, v: Double): SendFiberCommand = {
    val level = (v/2500.0 * 0xFFFF).toInt & 0xFFFF
    val bits = 0x00000 + (level << 3)
    makeCommand(fb, bits)
  }

  private def setDac0NoSelect(fb: FastBiasChannel, v: Double): SendFiberCommand = {
    val level = (v/2500.0 * 0xFFFF).toInt & 0xFFFF
    val bits = 0x00004 + (level << 3)
    makeCommand(fb, bits)
  }

  private def setDac1Fast(fb: FastBiasChannel, v: Double): SendFiberCommand = {
    val level = ((v+2500.0)/5000.0 * 0xFFFF).toInt & 0xFFFF
    val bits = 0x80000 + (level << 3)
    makeCommand(fb, bits)
  }

  private def setDac1Slow(fb: FastBiasChannel, v: Double): SendFiberCommand = {
    val level = ((v+2500.0)/5000.0 * 0xFFFF).toInt & 0xFFFF
    val bits = 0x80004 + (level << 3)
    makeCommand(fb, bits)
  }

  private def makeCommand(fb: FastBiasChannel, bits: Int): SendFiberCommand = {
    SendFiberCommand(fb.getFiberId(), bits)
  }
}
