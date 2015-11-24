package org.labrad.qubits.templates

import org.labrad.qubits.channels.Channel
import org.labrad.qubits.channels.PreampChannel
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.resources.PreampBoard
import org.labrad.qubits.resources.Resources

class PreampChannelBuilder(name: String, params: Seq[String], resources: Resources) extends ChannelBuilder {
  def build(): Channel = {
    val Seq(boardName, channel) = params
    val pc = new PreampChannel(name)
    val board = resources.get[PreampBoard](boardName)
    pc.setPreampBoard(board)
    pc.setPreampChannel(DcRackFiberId.fromString(channel))
    // look up the dacBoard on the other end and connect to it
    pc.setDacBoard(board.getDacBoard(DcRackFiberId.fromString(channel)))
    pc
  }
}
