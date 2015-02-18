package org.labrad.qubits.resources

import org.labrad.data.Data
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.enums.DeviceType
import scala.collection.JavaConverters._
import scala.reflect.ClassTag


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
  def get[T <: Resource](name: String)(implicit tag: ClassTag[T]): T = {
    resources.get(name) match {
      case Some(r: T) => r
      case Some(r) => sys.error(s"Resource $name has type ${r.getClass}; expected $tag")
      case None => sys.error(s"Resource $name not found")
    }
  }

  /**
   * Get all resources of a given type.
   * @param <T>
   * @param cls
   * @return
   */
  def getAll[T <: Resource : ClassTag]: Seq[T] = {
    resources.values.collect { case r: T => r }.toVector
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
  def updateWiring(resources: Seq[Data], fibers: Seq[Data], microwaves: Seq[Data]): Unit = {
    /*
     * resources - [(String type, String id),...]
     * fibers - [((dacName, fiber),(cardName, channel)),...]
     */
    // build resources for all objects
    val map = resources.map { elem =>
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
    for (elem <- fibers) {
      val dacName = elem.get(0, 0).getString()
      val fiber = elem.get(0, 1).getString()
      val cardName = elem.get(1, 0).getString()
      val channel = elem.get(1, 1).getString()

      val dac = r.get[DacBoard](dacName)
      val bias = r.get[BiasBoard](cardName)
      val df = DacFiberId.fromString(fiber)
      val bf = DcRackFiberId.fromString(channel)
      dac.setFiber(df, bias, bf)
      bias.setDacBoard(bf, dac, df)
    }

    // wire together microwave DAC boards and microwave sources
    for (elem <- microwaves) {
      val dacName = elem.get(0).getString()
      val devName = elem.get(1).getString()

      val dac = r.get[MicrowaveBoard](dacName)
      val uwaveSrc = r.get[MicrowaveSource](devName)
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
