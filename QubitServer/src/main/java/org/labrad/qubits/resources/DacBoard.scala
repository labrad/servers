package org.labrad.qubits.resources

import org.labrad.data.Data
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import scala.collection.JavaConverters._
import scala.collection.mutable

abstract class DacBoard(val name: String) extends Resource {
  private val fibers = mutable.Map.empty[DacFiberId, BiasBoard]
  private val fiberChannels = mutable.Map.empty[DacFiberId, DcRackFiberId]

  val buildType = "dacBuild" // either 'adcBuild' or 'dacBuild'
  protected var buildNumber: String = null
  protected val buildProperties = mutable.Map.empty[String, Long]
  protected var propertiesLoaded = false

  def getBuildType(): String = {
    buildType
  }

  def getBuildNumber(): String = {
    buildNumber
  }
  def setBuildNumber(buildNumber: String): Unit = {
    this.buildNumber = buildNumber
  }

  def loadProperties(properties: Data): Unit = {
    for (prop <- properties.getDataList().asScala) {
      val pair = prop.getClusterAsList()
      val propName = pair.get(0).getString()
      val propValue = pair.get(1).getWord()
      buildProperties.put(propName, propValue)
    }
    propertiesLoaded = true
  }

  def getBuildProperties(): Map[String, Long] = {
    buildProperties.toMap
  }
  def havePropertiesLoaded(): Boolean = {
    propertiesLoaded
  }

  def setFiber(fiber: DacFiberId, board: BiasBoard, channel: DcRackFiberId): Unit = {
    fibers.put(fiber, board)
    fiberChannels.put(fiber, channel)
  }
}
