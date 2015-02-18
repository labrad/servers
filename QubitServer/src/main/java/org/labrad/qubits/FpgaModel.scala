package org.labrad.qubits

import org.labrad.qubits.resources.DacBoard

trait FpgaModel {

  def name: String
  def getDacBoard(): DacBoard
  def getSequenceLength_us(): Double
  def getSequenceLengthPostSRAM_us(): Double
}
