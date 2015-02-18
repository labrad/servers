package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.TriggerChannel

abstract class TriggerDataBase extends TriggerData {

  private var channel: TriggerChannel = null

  def setChannel(channel: TriggerChannel): Unit = {
    this.channel = channel
  }

  def getChannel(): TriggerChannel = {
    channel
  }
}
