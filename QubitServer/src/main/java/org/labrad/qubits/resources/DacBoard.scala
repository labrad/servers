package org.labrad.qubits.resources

import org.labrad.data._
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import scala.collection.mutable

abstract class DacBoard(val name: String, val buildNumber: String, val buildProperties: Map[String, Long]) extends Resource {
  private val fibers = mutable.Map.empty[DacFiberId, BiasBoard]
  private val fiberChannels = mutable.Map.empty[DacFiberId, DcRackFiberId]

  val buildType = "dacBuild" // either 'adcBuild' or 'dacBuild'

  def getBuildType(): String = {
    buildType
  }

  def setFiber(fiber: DacFiberId, board: BiasBoard, channel: DcRackFiberId): Unit = {
    fibers.put(fiber, board)
    fiberChannels.put(fiber, channel)
  }
}
