package org.labrad.qubits.resources

object MicrowaveBoard {
  def create(name: String): MicrowaveBoard = {
    new MicrowaveBoard(name)
  }
}

class MicrowaveBoard(name: String) extends DacBoard(name) {
  private var uwaveSrc: MicrowaveSource = null

  def setMicrowaveSource(uwaves: MicrowaveSource): Unit = {
    this.uwaveSrc = uwaves
  }

  def getMicrowaveSource(): MicrowaveSource = {
    uwaveSrc
  }
}
