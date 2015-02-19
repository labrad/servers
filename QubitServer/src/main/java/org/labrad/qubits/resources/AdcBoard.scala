package org.labrad.qubits.resources

import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

object AdcBoard {
  def create(name: String, buildNumber: String, buildProperties: Map[String, Long]): Resource = {
    new AdcBoard(name, buildNumber, buildProperties)
  }
}

class AdcBoard(name: String, buildNumber: String, buildProperties: Map[String, Long]) extends DacBoard(name, buildNumber, buildProperties) with Resource {

  // replace "dacBuild" with "adcBuild"
  override val buildType = "adcBuild"

  override def setFiber(fiber: DacFiberId, board: BiasBoard, channel: DcRackFiberId): Unit = {
    sys.error(s"ADC board '$name' was given fibers!")
  }
}
