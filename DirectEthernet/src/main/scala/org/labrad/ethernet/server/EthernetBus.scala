package org.labrad.ethernet.server

import org.pcap4j.core._
import org.pcap4j.packet._
import org.pcap4j.packet.namednumber.EtherType
import org.pcap4j.util.MacAddress
import scala.collection.JavaConverters._
import scala.collection.mutable

trait Bus {
  def addListener(listener: EthernetPacket => Unit)
  def removeListener(listener: EthernetPacket => Unit)
  def send(packet: EthernetPacket)
}

class EthernetBus(
  device: PcapNetworkInterface,
  mode: PcapNetworkInterface.PromiscuousMode = PcapNetworkInterface.PromiscuousMode.PROMISCUOUS
) extends Bus {

  val name = device.getName
  val description = Option(device.getDescription)

  val macs = device.getLinkLayerAddresses.asScala.collect { case mac: MacAddress => mac }.toSeq

  // TODO: use weak references here instead?
  @volatile private var listeners = Set.empty[EthernetPacket => Unit]

  override def addListener(listener: EthernetPacket => Unit): Unit = synchronized {
    val _ = listenThread // force listen thread to start when first listener is added
    listeners += listener
  }

  override def removeListener(listener: EthernetPacket => Unit): Unit = synchronized {
    listeners -= listener
  }

  // Open the selected device
  private val snaplen = 0xFFFF // Capture all packets, no trucation
  private val timeout = 1 // minimal non-zero timeout, so listeners are invoked immediately

  private val pcap = device.openLive(snaplen, mode, timeout)
  private val sender = device.openLive(snaplen, mode, timeout)

  // Create a packet handler to receive packets from the libpcap loop.
  // The packet handler sends packets to all registered listeners.
  private val packetListener = new RawPacketListener {
    def gotPacket(bytes: Array[Byte]) {
      val ether = EthernetPacket.newPacket(bytes, 0, bytes.length)

      for (listener <- listeners) {
        listener(ether)
      }
    }
  }

  // listen thread is lazy, so it will be created and started on demand
  private lazy val listenThread = {
    val thread = new Thread {
      override def run(): Unit = {
        try {
          pcap.loop(-1, packetListener)
          pcap.close()
        } catch {
          case e: Exception =>
            // should never get here
            e.printStackTrace()
            throw e
        }
        // should never get here
        print(s"pcap loop exited unexpectedly for bus $name")
      }
    }
    thread.setDaemon(false)
    thread.start()
    thread
  }

  override def send(pkt: EthernetPacket): Unit = {
    sender.sendPacket(pkt)
  }
}

object RawEthernet {
  /**
   * Create a raw ethernet packet with the given source and destination mac
   * addresses, data and ether type. If no ether type is provided, we instead
   * use the data length to determine the ether type.
   */
  def apply(src: MacAddress, dst: MacAddress, data: Array[Byte], etherType: Option[EtherType] = None): EthernetPacket = {
    val et = etherType.getOrElse(EtherType.getInstance(data.length.toShort))
    new EthernetPacket.Builder()
        .srcAddr(src)
        .dstAddr(dst)
        .`type`(et)
        .paddingAtBuild(true)
        .payloadBuilder(new UnknownPacket.Builder().rawData(data))
        .build()
  }
}
