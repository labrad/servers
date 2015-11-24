package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.AnalogChannel

trait AnalogData extends Deconvolvable {
  def setChannel(channel: AnalogChannel): Unit
  def getDeconvolved(): Array[Int]
  def checkLength(expected: Int): Unit
}
