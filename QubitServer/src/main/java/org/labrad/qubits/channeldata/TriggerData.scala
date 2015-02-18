package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.TriggerChannel

trait TriggerData {
  def setChannel(channel: TriggerChannel): Unit
  def get(): Array[Boolean]
  def checkLength(expected: Int): Unit
}
