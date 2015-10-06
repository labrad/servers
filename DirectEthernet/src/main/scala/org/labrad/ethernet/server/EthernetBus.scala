package org.labrad.ethernet.server

import org.labrad.util.Logging
import org.pcap4j.core._
import org.pcap4j.packet._
import org.pcap4j.packet.namednumber.EtherType
import org.pcap4j.util.MacAddress
import scala.collection.JavaConverters._
import scala.collection.mutable
import scala.concurrent.{Await, Promise}
import scala.concurrent.duration._

trait Bus {
  def addListener(listener: EthernetPacket => Unit)
  def removeListener(listener: EthernetPacket => Unit)
  def send(packet: EthernetPacket, maxAttempts: Int = 2)
}

class EthernetBus(
  device: PcapNetworkInterface,
  mode: PcapNetworkInterface.PromiscuousMode = PcapNetworkInterface.PromiscuousMode.PROMISCUOUS
) extends Bus with Logging {

  val name = device.getName
  val description = Option(device.getDescription)

  val macs = device.getLinkLayerAddresses.asScala.collect { case mac: MacAddress => mac }.toSeq

  // TODO: use weak references here instead?
  @volatile private var listeners = Set.empty[EthernetPacket => Unit]

  override def addListener(listener: EthernetPacket => Unit): Unit = synchronized {
    val _ = listenThread // force listen thread to start when first listener is added
    Await.result(listenPromise.future, 5.seconds) // wait for listen thread to start
    listeners += listener
  }

  override def removeListener(listener: EthernetPacket => Unit): Unit = synchronized {
    listeners -= listener
  }

  // Open the selected device
  private val snaplen = 0xFFFF // Capture all packets, no trucation
  private val timeout = 1 // minimal non-zero timeout, so listeners are invoked immediately

  private var sender = device.openLive(snaplen, mode, timeout)

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
        var alive = true
        while (alive) {
          val pcap = reopen()
          try {
            listenPromise.trySuccess(())
            pcap.loop(-1, packetListener)
            log.warn(s"pcap loop exited unexpectedly. bus=$name")
          } catch {
            case e: InterruptedException =>
              log.info(s"pcap loop interrupted; exiting. bus=$name")
              alive = false
            case e: Exception =>
              log.error(s"error in listen thread. bus=$name", e)
          } finally {
            try {
              pcap.close()
            } catch {
              case e: Exception =>
                log.error(s"error while closing pcap handle. bus=$name", e)
            }
          }
        }
      }
    }
    thread.setName(s"EthernetBus-listenThread-$name")
    thread.setDaemon(false)
    thread.start()
    thread
  }

  // a promise that will be fired when the listenThread is running
  private val listenPromise = Promise[Unit]

  override def send(pkt: EthernetPacket, maxAttempts: Int = 2): Unit = {
    var sent = false
    var attempt = 0
    while (!sent && attempt < maxAttempts) {
      try {
        sender.sendPacket(pkt)
        sent = true
      } catch {
        case e: PcapNativeException =>
          log.error(s"error while sending packet. attempt=$attempt, bus=$name", e)
          sender = reopen()
      }
      attempt += 1
    }
    if (!sent) {
      sys.error(s"unable to send packet in $maxAttempts attempts. bus=$name")
    }
  }

  /**
   * Attempt to open a PcapHandle to the ethernet device for this bus.
   *
   * We retry up to the specified maximum number of attempts, with a pause of
   * the specified delay between failed attempts.
   */
  private def reopen(maxAttempts: Int = 10, delay: Duration = 1.second): PcapHandle = {
    var pcap: PcapHandle = null
    var attempt = 0
    while (pcap == null && attempt < maxAttempts) {
      if (attempt > 0) {
        Thread.sleep(delay.toMillis)
      }
      val device = Pcaps.getDevByName(name)
      if (device == null) {
        log.info(s"attempt=$attempt; failed to get device $name")
      } else {
        try {
          pcap = device.openLive(snaplen, mode, timeout)
        } catch {
          case e: PcapNativeException =>
            log.info(s"attempt=$attempt; failed to open pcap handle", e)
        }
      }
      attempt += 1
    }
    if (pcap == null) {
      sys.error(s"failed to reopen pcap handle in $maxAttempts attempts")
    }
    pcap
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
