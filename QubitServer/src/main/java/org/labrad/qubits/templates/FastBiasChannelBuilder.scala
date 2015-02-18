package org.labrad.qubits.templates

import org.labrad.qubits.channels.Channel
import org.labrad.qubits.channels.FastBiasFpgaChannel
import org.labrad.qubits.channels.FastBiasSerialChannel
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.resources.FastBias
import org.labrad.qubits.resources.Resources

class FastBiasChannelBuilder(name: String, params: Seq[String], resources: Resources) extends ChannelBuilder {
  def build(): Channel = {
    val Seq(boardName, channel) = params
    if (boardName.contains("FastBias")) {
      val fb = new FastBiasFpgaChannel(name)
      val board = resources.get[FastBias](boardName)
      fb.setFastBias(board)
      fb.setBiasChannel(DcRackFiberId.fromString(channel))
      fb.setDacBoard(board.getDacBoard(DcRackFiberId.fromString(channel)))
      fb
    } else {
      val fb = new FastBiasSerialChannel(name)
      fb.setDCRackCard(boardName.toInt)
      fb.setBiasChannel(DcRackFiberId.fromString(channel))
      fb
    }
  }
}
