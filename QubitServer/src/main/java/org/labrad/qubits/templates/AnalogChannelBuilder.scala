package org.labrad.qubits.templates

import org.labrad.qubits.channels.AnalogChannel
import org.labrad.qubits.channels.Channel
import org.labrad.qubits.enums.DacAnalogId
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.Resources

class AnalogChannelBuilder(name: String, params: Seq[String], resources: Resources) extends ChannelBuilder {
  def build(): Channel = {
    val Seq(boardName, dacId) = params
    val ch = new AnalogChannel(name)
    val board = resources.get[DacBoard](boardName)
    ch.setDacBoard(board)
    ch.setDacId(DacAnalogId.fromString(dacId))
    ch
  }
}
