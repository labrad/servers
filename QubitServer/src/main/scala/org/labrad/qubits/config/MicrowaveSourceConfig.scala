package org.labrad.qubits.config

import org.labrad.qubits.resources.MicrowaveSource

trait MicrowaveSourceConfig {
  def isOn: Boolean
  def frequency: Double
  def power: Double

  def setupPacket(src: MicrowaveSource): SetupPacket
}
