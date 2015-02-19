package org.labrad.qubits.templates

import org.labrad.data._
import org.labrad.qubits.Device
import org.labrad.qubits.resources.Resources

object DeviceBuilder {
  /**
   * Build a device template from a LabRAD data object.
   * @param template
   * @return
   */
  def fromData(template: Data, resources: Resources): DeviceBuilder = {
    val (name, channels) = template.get[(String, Seq[Data])]

    val channelBuilders = channels.map { channel =>
      ChannelBuilders.fromData(channel, resources)
    }
    new DeviceBuilder(name, channelBuilders)
  }
}

class DeviceBuilder(name: String, channelBuilders: Seq[ChannelBuilder]) {
  def build(): Device = {
    val dev = new Device(name)
    for (ct <- channelBuilders) {
      dev.addChannel(ct.build())
    }
    dev
  }
}
