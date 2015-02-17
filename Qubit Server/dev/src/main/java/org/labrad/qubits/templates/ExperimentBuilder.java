package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.qubits.Device;
import org.labrad.qubits.Experiment;
import org.labrad.qubits.resources.Resources;

import com.google.common.collect.Lists;

public class ExperimentBuilder {
  private final List<DeviceBuilder> deviceBuilders; 

  private ExperimentBuilder(List<DeviceBuilder> deviceBuilders) {
    this.deviceBuilders = deviceBuilders;
  }

  /**
   * Build a new experiment from this builder
   */
  public Experiment build() {
    List<Device> devs = Lists.newArrayList();
    for (DeviceBuilder dt : deviceBuilders) {
      devs.add(dt.create());
    }
    return new Experiment(devs);
  }

  /**
   * Return a new experiment builder for the specified devices
   * wired up according to the given wiring resource information.
   * @param devices
   * @param resources
   * @return
   */
  public static ExperimentBuilder fromData(Data devices, Resources resources) {
    List<DeviceBuilder> deviceBuilders = Lists.newArrayList();
    for (Data device : devices.getDataList()) {
      deviceBuilders.add(DeviceBuilder.fromData(device, resources));
    }
    return new ExperimentBuilder(deviceBuilders);
  }
}
