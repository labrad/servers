package org.labrad.qubits.templates

import org.labrad.qubits.channels.Channel
import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.resources.MicrowaveBoard
import org.labrad.qubits.resources.Resources

class IqChannelBuilder(name: String, params: Seq[String], resources: Resources) extends ChannelBuilder {
  def build(): Channel = {
    val Seq(boardName) = params
    val iq = new IqChannel(name)
    val board = resources.get[MicrowaveBoard](boardName)
    iq.setDacBoard(board)
    val src = board.getMicrowaveSource()
    iq.setMicrowaveSource(src)
    iq
  }
}
