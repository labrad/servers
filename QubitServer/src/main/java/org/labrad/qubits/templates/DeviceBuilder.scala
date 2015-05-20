package org.labrad.qubits.templates

import org.labrad.data.Data
import org.labrad.qubits.Device
import org.labrad.qubits.resources.Resources
import scala.collection.JavaConverters._

object DeviceBuilder {
  /**
   * Build a device template from a LabRAD data object.
   * @param template
   * @return
   */
  def fromData(template: Data, resources: Resources): DeviceBuilder = {
    val name = template.get(0).getString()
    val channels = template.get(1)

    val channelBuilders = channels.getDataList().asScala.toSeq.map { channel =>
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
