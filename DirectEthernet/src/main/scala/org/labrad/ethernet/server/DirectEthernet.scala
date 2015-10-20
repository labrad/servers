package org.labrad.ethernet.server

import org.labrad._
import org.labrad.annotations._
import org.labrad.data._
import org.labrad.errors.LabradException
import org.labrad.util.Logging
import org.pcap4j.core._
import org.pcap4j.packet.EthernetPacket
import org.pcap4j.packet.namednumber.EtherType
import org.pcap4j.util.MacAddress
import scala.collection.JavaConverters._
import scala.collection.mutable
import scala.concurrent.duration._

object DirectEthernet {
  def main(args: Array[String]): Unit = {
    val server = new DirectEthernet
    Server.run(server, args)
  }
}

class DirectEthernet extends Server[DirectEthernet, EthernetContext] {
  val name = "%LABRADNODE% Direct Ethernet"
  val doc = ""

  private val adapters = Pcaps.findAllDevs().asScala.toSeq

  // start listening on all interfaces
  val busses = adapters.map { a => new EthernetBus(a) }

  override def init(): Unit = {}

  def newContext(context: Context): EthernetContext = {
    new EthernetContext(cxn, this, context)
  }

  /**
   * Send a trigger signal to another context.
   */
  def sendTrigger(context: Context): Unit = {
    for (ctx <- this.get(context)) ctx.sendTrigger()
  }

  override def shutdown(): Unit = {}
}

class EthernetContext(cxn: Connection, server: DirectEthernet, context: Context)
extends ServerContext with Logging {

  import Filters._

  // context-specific state
  private var busOpt: Option[EthernetBus] = None

  private var writeSrcMac: Option[MacAddress] = None
  private var writeDstMac: Option[MacAddress] = None
  private var writeEtherType: Option[EtherType] = None

  private var readTimeout: Option[Duration] = None
  private val readFilters = mutable.Buffer.empty[Filter]

  private def fail(code: Int, message: String) = {
    throw new LabradException(code, message)
  }

  private def bus: EthernetBus = {
    busOpt.getOrElse { fail(10, s"Context: $context. Must connect to an adapter first") }
  }

  private def busMac: MacAddress = {
    bus.macs.headOption.getOrElse {
      MacAddress.getByName("00:00:00:00:00:00")
    }
  }

  // A queue to receive packets that pass filters.
  private val queue = new PacketQueue[EthernetPacket]

  private val listener: EthernetPacket => Unit = { pkt =>
    val accepted = readFilters.forall(f => f(pkt))
    if (accepted) {
      queue.enqueue(pkt)
    }
  }

  // A counter to track triggers sent by other contexts.
  private val triggerCounter = new TriggerCounter

  // macs are specified as strings or clusters of 6 bytes
  type MacParam = Either[String, (Long, Long, Long, Long, Long, Long)]

  private def parseMac(mac: MacParam): MacAddress = {
    mac match {
      case Left(s) => MacAddress.getByName(s)
      case Right((a, b, c, d, e, f)) =>
        MacAddress.getByAddress(Array(a, b, c, d, e, f).map(_.toByte))
    }
  }


  // life-cycle callbacks

  override def init(): Unit = {}

  override def expire(): Unit = {
    for (bus <- busOpt) bus.removeListener(listener)
    queue.clear(new Exception(s"context $context expired."))
    triggerCounter.clear(new Exception(s"context $context expired."))
  }


  // remotely-accessible settings

  @Setting(
    id = 1,
    name = "Adapters",
    doc = "Retrieves a list of available network adapters")
  def adapters(): Seq[(Long, String)] = {
    server.busses.zipWithIndex.map { case (b, i) => (i.toLong, b.name) }
  }

  @Setting(
    id = 10,
    name = "Connect",
    doc = """Connects to a network adapter
            |
            |After connecting to an adapter, packet filters should be added
            |followed by a request to Listen. If currently listening to another
            |adapter, we will stop listening and drop any enqueued packets.""")
  def connect(idxOrName: Either[Long, String]): String = {
    val bus = idxOrName match {
      case Left(index) => server.busses(index.toInt)
      case Right(name) => server.busses.find(_.name == name).get
    }
    // if connected to a different adapter previously, stop listening
    for (oldBus <- busOpt) {
      oldBus.removeListener(listener)
      clear()
    }
    busOpt = Some(bus)
    bus.name
  }

  @Setting(
    id = 20,
    name = "Listen",
    doc = "Starts listening for packets")
  def listen(): Unit = {
    bus.addListener(listener)
  }

  @Setting(
    id = 30,
    name = "Timeout",
    doc = "Sets the timeout for read operations")
  def timeout(@Accept("v[s]") duration: Double): Unit = {
    readTimeout = Some(duration.seconds)
  }

  @Setting(
    id = 40,
    name = "Collect",
    doc = """Waits for packets to arrive, but doesn't return them yet.
            |
            |After this call completes, a call to "Read" or "Read as Words" or
            |"Discard" with the same parameter will complete immediately.
            |
            |This setting is useful for pipelining since is allows a client
            |to wait for the completion of a task that returns a lot of data
            |and start the next task before retrieving the data generated in
            |the first task.""")
  def collect(numPackets: Long = 1): Unit = {
    val timeout = readTimeout.getOrElse { fail(11, "Read Timeout not set") }
    try {
      queue.await(numPackets, timeout)
    } catch {
      case e: java.util.concurrent.TimeoutException =>
        fail(12, s"Timeout! Failed to collect $numPackets packets after $timeout")
    }
  }

  @Setting(
    id = 50,
    name = "Read",
    doc = """Reads packets
            |
            |For each packet read, returns a tuple consisting of the Source MAC,
            |Destination MAC, Ether Type (-1 for IEEE 802.3) and Data of the
            |received packet as a byte string""")
  def read(numPackets: Long = 1): Seq[(String, String, Int, Array[Byte])] = {
    collect(numPackets)
    val results = queue.take(numPackets.toInt)
    results.map { pkt =>
      val src = pkt.getHeader.getSrcAddr
      val dst = pkt.getHeader.getDstAddr
      val typ = pkt.getHeader.getType.value.toInt
      val data = pkt.getPayload.getRawData

      (src.toString.toUpperCase, dst.toString.toUpperCase, typ, data)
    }
  }

  @Setting(
    id = 51,
    name = "Read as Words",
    doc = """Reads packets
            |
            |For each packet read, returns a tuple consisting of the Source MAC,
            |Destination MAC, Ether Type (-1 for IEEE 802.3) and Data of the
            |packet as an array of words.""")
  def readAsWords(numPackets: Long = 1): Seq[(String, String, Int, Array[Long])] = {
    read(numPackets).map { case (src, dst, typ, data) =>
      (src, dst, typ, data.map(_ & 0xffL))
    }
  }

  @Setting(
    id = 52,
    name = "Discard",
    doc = """Waits for packets and deletes them from the queue
            |
            |This setting behaves exactly like "Read", except is does not return
            |the content of the recieved packets""")
  def discard(numPackets: Long = 1): Unit = {
    collect(numPackets)
    queue.drop(numPackets.toInt)
  }

  @Setting(
    id = 55,
    name = "Clear",
    doc = "Clears all pending packets out of the buffer")
  def clear(): Unit = {
    queue.clear()
  }


  @Setting(
    id = 60,
    name = "Source MAC",
    doc = """Sets the Source MAC to be used for subsequent Writes
            |
            |Returns the source MAC as a string "01:23:45:67:89:AB".""")
  def srcMac(): String = {
    // Use adapter MAC as source (default)
    val addr = busMac
    writeSrcMac = None
    addr.toString.toUpperCase
  }

  def srcMac(mac: MacParam): String = {
    val addr = parseMac(mac)
    writeSrcMac = Some(addr)
    addr.toString.toUpperCase
  }

  @Setting(
    id = 61,
    name = "Destination MAC",
    doc = """Sets the Destination MAC to be used for subsequent Writes
            |
            |Returns the source MAC as a string "01:23:45:67:89:AB".""")
  def destMac(mac: MacParam): String = {
    val addr = parseMac(mac)
    writeDstMac = Some(addr)
    addr.toString.toUpperCase
  }

  @Setting(
    id = 62,
    name = "Ether Type",
    doc = """Sets the Ether Type to be used for subsequent Writes
            |
            |If ether type is given as None, packets will be sent as raw
            |ethernet packets with the ether type field set to the payload
            |length in bytes.""")
  def etherType(typ: Option[Int]): Unit = {
    writeEtherType = typ.map(t => EtherType.getInstance(t.toShort))
  }

  @Setting(
    id = 65,
    name = "Write",
    doc = "Sends packets")
  def write(data: Either[Array[Byte], Array[Long]]): Unit = {
    val bytes = data match {
      case Left(bytes) => bytes
      case Right(words) => words.map(_.toByte)
    }

    val srcMac = writeSrcMac.getOrElse { busMac }
    val dstMac = writeDstMac.getOrElse { fail(13, "Must specify destination MAC address before write") }
    val etherType = writeEtherType

    val packet = RawEthernet(srcMac, dstMac, bytes, etherType)
    bus.send(packet)
  }


  @Setting(
    id = 100,
    name = "Require Source MAC",
    doc = "Sets the Source MAC that a packet has to match to be accepted")
  def requireSrcMac(mac: MacParam): String = {
    val addr = parseMac(mac)
    readFilters += RequireSrcMac(addr)
    addr.toString.toUpperCase
  }

  @Setting(
    id = 101,
    name = "Reject Source MAC",
    doc = "If a packet's Source MAC matches, it will be rejected")
  def rejectSrcMac(mac: MacParam): String = {
    val addr = parseMac(mac)
    readFilters += RejectSrcMac(addr)
    addr.toString.toUpperCase
  }

  @Setting(
    id = 110,
    name = "Require Destination MAC",
    doc = "Sets the Destination MAC that a packet has to match to be accepted")
  def requireDstMac(mac: MacParam): String = {
    val addr = parseMac(mac)
    readFilters += RequireDstMac(addr)
    addr.toString.toUpperCase
  }

  @Setting(
    id = 111,
    name = "Reject Destination MAC",
    doc = "If a packet's Destination MAC matches, it will be rejected")
  def rejectDstMac(mac: MacParam): String = {
    val addr = parseMac(mac)
    readFilters += RejectDstMac(addr)
    addr.toString.toUpperCase
  }

  @Setting(
    id = 120,
    name = "Require Length",
    doc = "Only packets of this length will be accepted")
  def requireLength(len: Long): Unit = {
    readFilters += RequireLength(len.toInt)
  }

  @Setting(
    id = 121,
    name = "Reject Length",
    doc = "Packets of this length will be rejected")
  def rejectLength(len: Long): Unit = {
    readFilters += RejectLength(len.toInt)
  }

  @Setting(
    id = 130,
    name = "Require Ether Type",
    doc = "Only packets with this Ether Type will be accepted")
  def requireEtherType(typ: Int): Unit = {
    typ.toShort match {
      case -1 => readFilters += RequireRawEtherType
      case t => readFilters += RequireEtherType(EtherType.getInstance(t))
    }
  }

  @Setting(
    id = 131,
    name = "Reject Ether Type",
    doc = "Packets with this Ether Type will be rejected")
  def rejectEtherType(typ: Int): Unit = {
    typ.toShort match {
      case -1 => readFilters += RejectRawEtherType
      case t => readFilters += RejectEtherType(EtherType.getInstance(t))
    }
  }

  @Setting(
    id = 140,
    name = "Require Content",
    doc = "The packet content needs to match for the packet to be accepted")
  def requireContent(offset: Long, data: Either[Array[Byte], Array[Long]]): Unit = {
    val pattern = data match {
      case Left(bytes) => bytes
      case Right(words) => words.map(_.toByte)
    }
    readFilters += RequireContent(offset.toInt, pattern)
  }

  @Setting(
    id = 141,
    name = "Reject Content",
    doc = "If the packet content matches, the packet will be rejected")
  def rejectContent(offset: Long, data: Either[Array[Byte], Array[Long]]): Unit = {
    val pattern = data match {
      case Left(bytes) => bytes
      case Right(words) => words.map(_.toByte)
    }
    readFilters += RejectContent(offset.toInt, pattern)
  }


  @Setting(
    id = 200,
    name = "Send Trigger",
    doc = """Sends a trigger signal to the specified context to release it from a "Wait for Trigger" call.
            |
            |This setting helps to control timing between different contexts to assist pipelining.
            |If this trigger is the final one missing to release a "Wait For Trigger" call,
            |execution is passed into the waiting Context before the call to this setting completes.""")
  def sendTrigger(req: RequestContext, triggerContext: (Long, Long)): Unit = {
    val (high, low) = triggerContext match {
      case (0, low) => (req.source, low)
      case (high, low) => (high, low)
    }
    log.debug(s"sending trigger from $context to ($high, $low)")
    server.sendTrigger(Context(high, low))
  }

  // called when another context is sending us a trigger
  private[ethernet] def sendTrigger(): Unit = {
    log.debug(s"got trigger: ctx=${context}")
    triggerCounter.trigger()
  }

  @Setting(
    id = 201,
    name = "Wait for Trigger",
    doc = """Waits for trigger signals to be sent to this context with "Send Trigger".
            |
            |This setting helps to control timing between different contexts to assist pipelining.
            |The return value can be used to investigate performance of pipelined operations.
            |If all required triggers had already been received before this setting was called,
            |the return value is 0 and most likely indicates that the pipe was no longer filled.""")
  @Return("v[s]")
  def awaitTrigger(numTriggers: Long = 1, @Accept("v[s]") timeout: Double = 3600): Double = {
    log.debug(s"awaiting $numTriggers triggers in context $context")
    val elapsed = triggerCounter.await(numTriggers, timeout.seconds)
    elapsed.toNanos / 1e9
  }
}
