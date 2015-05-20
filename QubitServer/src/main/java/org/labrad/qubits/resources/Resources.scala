package org.labrad.qubits.resources

import java.util.List

import org.labrad.data.Data
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.enums.DeviceType
import scala.collection.JavaConverters._

import com.google.common.collect.Lists


/**
 * "Resources represent the available hardware; these are configured in the registry."
 *
 * @author maffoo
 */
class Resources protected(resources: Map[String, Resource]) {

  /**
   * Get a resource by name, ensuring that it is of a particular type
   * @param <T>
   * @param name
   * @param cls
   * @return
   */
  def get[T <: Resource](name: String, cls: Class[T]): T = {
    require(resources.contains(name), s"Resource '$name' not found")
    val r = resources(name)
    require(cls.isInstance(r), s"Resource '$name' has type ${r.getClass}; expected $cls")
    r.asInstanceOf[T]
  }

  /**
   * Get all resources of a given type.
   * @param <T>
   * @param cls
   * @return
   */
  def getAll[T <: Resource](cls: Class[T]): List[T] = {
    val list: List[T] = Lists.newArrayList()
    for (r <- resources.values) {
      if (cls.isInstance(r)) {
        list.add(r.asInstanceOf[T])
      }
    }
    list
  }
}

object Resources {

  /**
   * Create a resource of the given type.
   * @param type
   * @param name
   * @return
   */
  def create(devType: DeviceType, name: String, properties: Seq[Data]): Resource = {
    import DeviceType._
    devType match {
      case UWAVEBOARD => MicrowaveBoard.create(name)
      case ANALOGBOARD => AnalogBoard.create(name)
      case FASTBIAS => FastBias.create(name, properties)
      case PREAMP => PreampBoard.create(name)
      case UWAVESRC => MicrowaveSource.create(name)
      case ADCBOARD => AdcBoard.create(name)
      case _ => sys.error(s"Invalid resource type: $devType")
    }
  }
  /**
   * Create new wiring configuration and update the current config.
   * @param resources
   * @param fibers
   * @param microwaves
   */
  def updateWiring(resources: List[Data], fibers: List[Data], microwaves: List[Data]): Unit = {
    /*
     * resources - [(String type, String id),...]
     * fibers - [((dacName, fiber),(cardName, channel)),...]
     */
    // build resources for all objects
    val map = resources.asScala.map { elem =>
      val devType = elem.get(0).getString()
      val name = elem.get(1).getString()
      val properties = if (elem.getClusterSize() == 3) {
        elem.get(2).getClusterAsList().asScala
      } else {
        Nil
      }
      val dt = DeviceType.fromString(devType)
      name -> create(dt, name, properties)
    }.toMap
    val r = new Resources(map)

    // wire together DAC boards and bias boards
    for (elem <- fibers.asScala) {
      val dacName = elem.get(0, 0).getString()
      val fiber = elem.get(0, 1).getString()
      val cardName = elem.get(1, 0).getString()
      val channel = elem.get(1, 1).getString()

      val dac = r.get(dacName, classOf[DacBoard])
      val bias = r.get(cardName, classOf[BiasBoard])
      val df = DacFiberId.fromString(fiber)
      val bf = DcRackFiberId.fromString(channel)
      dac.setFiber(df, bias, bf)
      bias.setDacBoard(bf, dac, df)
    }

    // wire together microwave DAC boards and microwave sources
    for (elem <- microwaves.asScala) {
      val dacName = elem.get(0).getString()
      val devName = elem.get(1).getString()

      val dac = r.get(dacName, classOf[MicrowaveBoard])
      val uwaveSrc = r.get(devName, classOf[MicrowaveSource])
      dac.setMicrowaveSource(uwaveSrc)
      uwaveSrc.addMicrowaveBoard(dac)
    }

    // Set this new resource map as the current one
    setCurrent(r)
  }

  // we keep a single instance containing the current resource map.
  // updates to this instance are protected by a thread lock
  private var current: Resources = null
  private val updateLock = new Object()

  /**
   * Set a new resource collection as the current collection
   * @param resources
   */
  private def setCurrent(resources: Resources): Unit = {
    updateLock.synchronized {
      current = resources
    }
  }

  /**
   * Get the current resource collection
   * @return
   */
  def getCurrent(): Resources = {
    updateLock.synchronized {
      current
    }
  }
}
