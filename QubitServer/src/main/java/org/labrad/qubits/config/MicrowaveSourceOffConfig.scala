package org.labrad.qubits.config

import org.labrad.data.Data
import org.labrad.qubits.resources.MicrowaveSource

case object MicrowaveSourceOffConfig extends MicrowaveSourceConfig {

  override def frequency: Double = {
    6.0 // return a default frequency for the sake of deconvolution
    //throw new RuntimeException("Microwaves are off");
  }

  override def power: Double = {
    sys.error("Microwaves are off")
  }

  override def isOn: Boolean = {
    false
  }

  override def getSetupPacket(src: MicrowaveSource): SetupPacket = {
    val data = Data.ofType("(ss)(sb)")
    data.get(0).setString("Select Device", 0).setString(src.getDevice, 1)
    data.get(1).setString("Output", 0).setBool(false, 1)

    val state = s"${src.getName}: off"
    new SetupPacket(state, data)
  }
}
