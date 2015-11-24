package org.labrad.qubits.resources

object AnalogBoard {
  def create(name: String, buildNumber: String, buildProperties: Map[String, Long]): AnalogBoard = {
    new AnalogBoard(name, buildNumber, buildProperties)
  }
}

class AnalogBoard(name: String, buildNumber: String, buildProperties: Map[String, Long]) extends DacBoard(name, buildNumber, buildProperties)
