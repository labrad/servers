package org.labrad.qubits.resources

import java.util.Map

import org.labrad.data.Data
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import scala.collection.JavaConverters._

import com.google.common.collect.Maps

abstract class DacBoard(name: String) extends Resource {
  private val fibers: Map[DacFiberId, BiasBoard] = Maps.newHashMap()
  private val fiberChannels: Map[DacFiberId, DcRackFiberId] = Maps.newHashMap()

  protected var buildType: String = "dacBuild" // either 'adcBuild' or 'dacBuild'
  protected var buildNumber: String = null
  protected val buildProperties: Map[String, java.lang.Long] = Maps.newHashMap()
  protected var propertiesLoaded = false

  def getName(): String = {
    name
  }

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
    this.propertiesLoaded = true
  }

  def getBuildProperties(): Map[String, java.lang.Long] = {
    this.buildProperties
  }
  def havePropertiesLoaded(): Boolean = {
    this.propertiesLoaded
  }

  def setFiber(fiber: DacFiberId, board: BiasBoard, channel: DcRackFiberId): Unit = {
    fibers.put(fiber, board)
    fiberChannels.put(fiber, channel)
  }
}
