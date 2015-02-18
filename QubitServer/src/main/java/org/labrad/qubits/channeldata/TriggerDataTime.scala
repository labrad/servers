package org.labrad.qubits.channeldata

class TriggerDataTime(vals: Array[Boolean]) extends TriggerDataBase {

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(vals.length, expected)
  }

  override def get(): Array[Boolean] = {
    vals
  }
}
