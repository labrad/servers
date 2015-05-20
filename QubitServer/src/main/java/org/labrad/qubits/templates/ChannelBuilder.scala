package org.labrad.qubits.templates

import org.labrad.qubits.channels.Channel

trait ChannelBuilder {
  def build(): Channel
}
