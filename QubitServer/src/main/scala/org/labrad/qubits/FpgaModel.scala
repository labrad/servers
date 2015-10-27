package org.labrad.qubits

import org.labrad.qubits.resources.DacBoard

trait FpgaModel {

  def name: String
  def dacBoard: DacBoard
  def sequenceLength_us: Double
  def sequenceLengthPostSRAM_us: Double
}
