package org.labrad.qubits.config

import org.labrad.data.Data
import org.labrad.qubits.resources.MicrowaveSource

case class MicrowaveSourceOnConfig(frequency: Double, power: Double) extends MicrowaveSourceConfig {

  override def isOn: Boolean = {
    true
  }

  override def getSetupPacket(src: MicrowaveSource): SetupPacket = {
    val data = Data.ofType("(ss)(sb)(sv[GHz])(sv[dBm])")
    data.get(0).setString("Select Device", 0).setString(src.name, 1)
    data.get(1).setString("Output", 0).setBool(true, 1)
    data.get(2).setString("Frequency", 0).setValue(frequency, 1)
    data.get(3).setString("Amplitude", 0).setValue(power, 1)

    val state = s"${src.name}: $frequency GHz @ $power dBm"
    new SetupPacket(state, data)
  }
}
