package org.labrad.qubits.templates

import org.labrad.qubits.channels.AdcChannel
import org.labrad.qubits.channels.Channel
import org.labrad.qubits.resources.AdcBoard
import org.labrad.qubits.resources.Resources

class AdcChannelBuilder(name: String, params: Seq[String], resources: Resources) extends ChannelBuilder {
  def build(): Channel = {
    val Seq(boardName) = params
    val board = resources.get[AdcBoard](boardName)
    new AdcChannel(name, board)
  }
}
