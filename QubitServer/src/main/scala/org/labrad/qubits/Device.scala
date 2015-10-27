package org.labrad.qubits

import org.labrad.qubits.channels.Channel
import scala.collection.mutable
import scala.reflect.ClassTag

/**
 * Model of a device, essentially a collection of named channels of various types.
 * Each channel connects various physical devices (FastBias, Preamp, GHzDac) to some
 * controllable parameter on the device (flux bias, microwave, etc.).
 *
 * @author maffoo
 */
class Device(val name: String, val channels: Seq[Channel]) {

  private val channelsByName = channels.map(ch => ch.name -> ch).toMap

  /**
   * Get all defined channels.
   * @return
   */
  def getChannels(): Seq[Channel] = {
    channels
  }

  /**
   * Get all channels of a particular type.
   * @param <T>
   * @param cls
   * @return
   */
  def getChannels[T <: Channel : ClassTag]: Seq[T] = {
    channels.collect { case ch: T => ch }
  }

  /**
   * Get a channel by name (of any type).
   * @param name
   * @return
   */
  def getAnyChannel(name: String): Channel = {
    channelsByName.getOrElse(name, sys.error(s"Device ${this.name} has no channel named $name"))
  }

  /**
   * Get a channel by name and type.
   * @param <T>
   * @param name
   * @param cls
   * @return
   */
  def getChannel[T <: Channel](name: String)(implicit tag: ClassTag[T]): T = {
    getAnyChannel(name) match {
      case ch: T => ch
      case _ => sys.error(s"Channel $name is not of type $tag")
    }
  }

  /**
   * Get a channel by type only.  This fails if there is more than one channel with the desired type.
   * @param <T>
   * @param cls
   * @return
   */
  def getChannel[T <: Channel](implicit tag: ClassTag[T]): T = {
    getChannels[T] match {
      case Seq(ch) => ch
      case Seq() => sys.error(s"Device $name has no channel of type $tag")
      case _ => sys.error(s"Device $name has more than one channel of type $tag")
    }
  }
}
