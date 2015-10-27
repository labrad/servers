package org.labrad.qubits.channels

import org.labrad.qubits.resources.DacBoard

/**
 * A TimingChannel is one that has a DAC board or ADC board that can be added to the timing order.
 * It doesn't need to specify much; it's more of an internal designation than anything else.
 *
 * Previously the list of boards to be added to the timing order was drawn from preamp channels;
 * now we also need to include ADCs. Both {@link PreampChannel} and {@link AdcChannel} implement this.
 *
 * @author pomalley
 *
 */
trait TimingChannel extends FpgaChannel {
  def dacBoard: DacBoard

  def demodChannel: Int
}
