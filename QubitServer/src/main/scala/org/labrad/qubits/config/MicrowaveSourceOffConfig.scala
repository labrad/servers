package org.labrad.qubits.config

import org.labrad.data._
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
    val data = Seq(
      "Select Device" -> Str(src.name),
      "Output" -> Bool(false)
    )

    val state = s"${src.name}: off"
    SetupPacket(state, data)
  }
}
