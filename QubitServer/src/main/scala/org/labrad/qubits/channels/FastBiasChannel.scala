package org.labrad.qubits.channels

import org.labrad.qubits.Experiment
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.resources.FastBias

class FastBiasChannel(val name: String, val fiberId: DcRackFiberId) extends FiberChannel {

  protected var expt: Experiment = null
  protected var fb: FastBias = null

  def setFastBias(fb: FastBias): Unit = {
    this.fb = fb
  }

  def getFastBias(): FastBias = {
    fb
  }

  def setExperiment(expt: Experiment): Unit = {
    this.expt = expt
  }

  def getExperiment(): Experiment = {
    expt
  }

  def getDcFiberId(): DcRackFiberId = {
    fiberId
  }

  def getFiberId(): DacFiberId = {
    fb.getFiber(fiberId)
  }

  def clearConfig(): Unit = {
    // nothing to do here
  }

}
