package org.labrad.qubits.channels

/**
 * Represents channels that can implement the start delay function.
 * @author pomalley
 *
 */
trait StartDelayChannel extends FpgaChannel {
  def setStartDelay(startDelay: Int): Unit
  def startDelay: Int
}
