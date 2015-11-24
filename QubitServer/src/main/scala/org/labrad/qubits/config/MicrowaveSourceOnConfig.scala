package org.labrad.qubits.config

import org.labrad.data._
import org.labrad.qubits.resources.MicrowaveSource

case class MicrowaveSourceOnConfig(frequency: Double, power: Double) extends MicrowaveSourceConfig {

  override def isOn: Boolean = {
    true
  }

  override def getSetupPacket(src: MicrowaveSource): SetupPacket = {
    val data = Seq(
      "Select Device" -> Str(src.name),
      "Output" -> Bool(true),
      "Frequency" -> Value(frequency, "GHz"),
      "Amplitude" -> Value(power, "dBm")
    )

    val state = s"${src.name}: $frequency GHz @ $power dBm"
    SetupPacket(state, data)
  }
}
