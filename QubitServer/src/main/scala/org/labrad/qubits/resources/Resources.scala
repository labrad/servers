package org.labrad.qubits.resources

import org.labrad.data._
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.enums.DeviceType
import scala.reflect.ClassTag

/**
 * "Resources represent the available hardware; these are configured in the registry."
 *
 * @author maffoo
 */
class Resources(resources: Map[String, Resource]) {

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
   * Create new wiring resource configuration.
   * @param resources
   * @param fibers
   * @param microwaves
   */
  def create(
    resources: Seq[Data],
    fibers: Seq[Data],
    microwaves: Seq[Data],
    adcBuildNums: Map[String, String],
    dacBuildNums: Map[String, String],
    adcBuildProps: Map[String, Map[String, Long]],
    dacBuildProps: Map[String, Map[String, Long]]
  ): Resources = {
    /*
     * resources - [(String type, String id),...]
     * fibers - [((dacName, fiber),(cardName, channel)),...]
     */
    // build resources for all objects
    val map = resources.map { elem =>
      val (devType, name, properties) = elem match {
        case Cluster(Str(devType), Str(name)) => (devType, name, Nil)
        case Cluster(Str(devType), Str(name), Cluster(props @ _*)) => (devType, name, props)
      }
      val dt = DeviceType.fromString(devType)
      name -> Resource.create(dt, name, properties, adcBuildNums, dacBuildNums, adcBuildProps, dacBuildProps)
    }.toMap
    val r = new Resources(map)

    // wire together DAC boards and bias boards
    for (elem <- fibers) {
      val ((dacName, fiber), (cardName, channel)) =
          elem.get[((String, String), (String, String))]

      val dac = r.get[DacBoard](dacName)
      val bias = r.get[BiasBoard](cardName)
      val df = DacFiberId.fromString(fiber)
      val bf = DcRackFiberId.fromString(channel)
      dac.setFiber(df, bias, bf)
      bias.setDacBoard(bf, dac, df)
    }

    // wire together microwave DAC boards and microwave sources
    for (elem <- microwaves) {
      val (dacName, devName) = elem.get[(String, String)]

      val dac = r.get[MicrowaveBoard](dacName)
      val uwaveSrc = r.get[MicrowaveSource](devName)
      dac.setMicrowaveSource(uwaveSrc)
      uwaveSrc.addMicrowaveBoard(dac)
    }

    r
  }
}
