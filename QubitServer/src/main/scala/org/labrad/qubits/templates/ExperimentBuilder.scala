package org.labrad.qubits.templates

import org.labrad.data.Data
import org.labrad.qubits.Experiment
import org.labrad.qubits.resources.Resources

object ExperimentBuilder {
  /**
   * Return a new experiment builder for the specified devices
   * wired up according to the given wiring resource information.
   * @param devices
   * @param resources
   * @return
   */
  def fromData(devices: Data, resources: Resources): ExperimentBuilder = {
    val deviceBuilders = devices.get[Seq[Data]].map { device =>
      DeviceBuilder.fromData(device, resources)
    }
    new ExperimentBuilder(deviceBuilders)
  }
}

class ExperimentBuilder(deviceBuilders: Seq[DeviceBuilder]) {
  def build(): Experiment = {
    val devs = deviceBuilders.map(_.build())
    new Experiment(devs)
  }
}
