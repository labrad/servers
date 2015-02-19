package org.labrad.qubits.resources

object MicrowaveBoard {
  def create(name: String, buildNumber: String, buildProperties: Map[String, Long]): MicrowaveBoard = {
    new MicrowaveBoard(name, buildNumber, buildProperties)
  }
}

class MicrowaveBoard(name: String, buildNumber: String, buildProperties: Map[String, Long]) extends DacBoard(name, buildNumber, buildProperties) {
  private var uwaveSrc: MicrowaveSource = null

  def setMicrowaveSource(uwaves: MicrowaveSource): Unit = {
    this.uwaveSrc = uwaves
  }

  def getMicrowaveSource(): MicrowaveSource = {
    uwaveSrc
  }
}
