package org.labrad.qubits.resources

import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

object AdcBoard {
  def create(name: String): Resource = {
    new AdcBoard(name)
  }
}

class AdcBoard(name: String) extends DacBoard(name) with Resource {

  // replace "dacBuild" with "adcBuild"
  buildType = "adcBuild"

  override def setFiber(fiber: DacFiberId, board: BiasBoard, channel: DcRackFiberId): Unit = {
    sys.error(s"ADC board '$name' was given fibers!")
  }
}
