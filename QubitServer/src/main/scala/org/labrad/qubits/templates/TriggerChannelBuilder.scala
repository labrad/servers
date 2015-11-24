package org.labrad.qubits.templates

import org.labrad.qubits.channels.Channel
import org.labrad.qubits.channels.TriggerChannel
import org.labrad.qubits.enums.DacTriggerId
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.Resources

class TriggerChannelBuilder(name: String, params: Seq[String], resources: Resources) extends ChannelBuilder {
  def build(): Channel = {
    val Seq(boardName, triggerId) = params
    val tc = new TriggerChannel(name)
    val board = resources.get[DacBoard](boardName)
    tc.setDacBoard(board)
    tc.setTriggerId(DacTriggerId.fromString(triggerId))
    tc
  }
}
