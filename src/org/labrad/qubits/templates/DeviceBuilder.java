package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.qubits.Device;
import org.labrad.qubits.resources.Resources;

import com.google.common.collect.Lists;

public class DeviceBuilder {
  private final String name;
  private final List<ChannelBuilder> channels;

  private DeviceBuilder(String name, List<ChannelBuilder> channelBuilders) {
    this.name = name;
    channels = channelBuilders;
  }

  public String getName() {
    return name;
  }

  public Device create() {
    Device dev = new Device(name);
    for (ChannelBuilder ct : channels) {
      dev.addChannel(ct.build());
    }
    return dev;
  }

  /**
   * Build a device template from a LabRAD data object.
   * @param template
   * @return
   */
  public static DeviceBuilder fromData(Data template, Resources resources) {
    String name = template.get(0).getString();
    Data channels = template.get(1);

    List<ChannelBuilder> channelBuilders = Lists.newArrayList();
    for (Data channel : channels.getDataList()) {
      channelBuilders.add(ChannelBuilders.fromData(channel, resources));
    }
    return new DeviceBuilder(name, channelBuilders);
  }
}
