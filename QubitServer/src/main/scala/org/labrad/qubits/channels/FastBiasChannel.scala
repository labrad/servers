package org.labrad.qubits.channels

import org.labrad.qubits.Experiment
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.resources.FastBias

class FastBiasChannel(val name: String, val dcRackFiberId: DcRackFiberId) extends FiberChannel {

  protected var fb: FastBias = null

  def setFastBias(fb: FastBias): Unit = {
    this.fb = fb
  }

  def fastBias: FastBias = {
    fb
  }

  def dacFiberId: DacFiberId = {
    fb.dacFiber(dcRackFiberId)
  }

  def clearConfig(): Unit = {
    // nothing to do here
  }

}
