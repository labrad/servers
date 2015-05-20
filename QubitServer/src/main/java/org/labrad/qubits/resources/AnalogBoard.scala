package org.labrad.qubits.resources

object AnalogBoard {
  def create(name: String): AnalogBoard = {
    new AnalogBoard(name)
  }
}

class AnalogBoard(name: String) extends DacBoard(name)
