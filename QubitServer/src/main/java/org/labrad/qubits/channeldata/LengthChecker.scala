package org.labrad.qubits.channeldata

object LengthChecker {
  def checkLengths(actual: Int, expected: Int): Unit = {
    require(actual == expected,
        s"Incorrect SRAM block length: expected $expected but got $actual")
  }
}
