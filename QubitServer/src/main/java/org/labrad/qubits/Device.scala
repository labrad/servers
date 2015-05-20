package org.labrad.qubits

import com.google.common.collect.Lists
import com.google.common.collect.Maps
import java.util.List
import java.util.Map
import org.labrad.qubits.channels.Channel
import scala.collection.JavaConverters._

/**
 * Model of a device, essentially a collection of named channels of various types.
 * Each channel connects various physical devices (FastBias, Preamp, GHzDac) to some
 * controllable parameter on the device (flux bias, microwave, etc.).
 * 
 * @author maffoo
 */
class Device(name: String) {

  private val channels: List[Channel] = Lists.newArrayList()
  private val channelsByName: Map[String, Channel] = Maps.newHashMap()

  def getName(): String = {
    name
  }

  /**
   * Add a channel to this device.
   * @param ch
   */
  def addChannel(ch: Channel): Unit = {
    channels.add(ch)
    channelsByName.put(ch.getName(), ch)
  }

  /**
   * Get all defined channels.
   * @return
   */
  def getChannels(): List[Channel] = {
    Lists.newArrayList(channels)
  }

  /**
   * Get all channels of a particular type.
   * @param <T>
   * @param cls
   * @return
   */
  def getChannels[T <: Channel](cls: Class[T]): List[T] = {
    val matches: List[T] = Lists.newArrayList()
    for (chan <- channels.asScala) {
      if (cls.isInstance(chan)) {
        matches.add(chan.asInstanceOf[T])
      }
    }
    matches
  }

  /**
   * Get a channel by name (of any type).
   * @param name
   * @return
   */
  def getChannel(name: String): Channel = {
    require(channelsByName.containsKey(name),
        s"Device '$getName' has no channel named '$name'")
    channelsByName.get(name)
  }

  /**
   * Get a channel by name and type.
   * @param <T>
   * @param name
   * @param cls
   * @return
   */
  def getChannel[T <: Channel](name: String, cls: Class[T]): T = {
    val ch = getChannel(name)
    require(cls.isInstance(ch),
        s"Channel '$name' is not of type '${cls.getName}'")
    ch.asInstanceOf[T]
  }

  /**
   * Get a channel by type only.  This fails if there is more than one channel with the desired type.
   * @param <T>
   * @param cls
   * @return
   */
  def getChannel[T <: Channel](cls: Class[T]): T = {
    val channels = getChannels(cls)
    require(channels.size() == 1,
        s"Device '$getName' has more than one channel of type '${cls.getName}'")
    channels.get(0)
  }
}
