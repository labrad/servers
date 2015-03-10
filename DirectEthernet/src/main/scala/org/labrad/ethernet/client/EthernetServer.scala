package org.labrad.ethernet.client

import org.labrad._
import org.labrad.data._
import scala.concurrent.Future
import scala.concurrent.duration._

trait EthernetServer extends Requester {
  def adapters(): Future[Seq[(Long, String)]] =
    call("Adapters").map { _.get[Seq[(Long, String)]] }

  def connect(name: String): Future[String] = call("Connect", Str(name)).map { _.get[String] }
  def timeout(seconds: Duration): Future[Unit] = callUnit("Timeout", Value(seconds.toMillis.toDouble, "ms"))
  def listen(): Future[Unit] = callUnit("Listen")

  def read(packets: Long): Future[Seq[(String, String, Int, Array[Byte])]] = {
    call("Read", UInt(packets)).map { _.get[Seq[(String, String, Int, Array[Byte])]] }
  }
  def write(bytes: Array[Byte]): Future[Unit] = callUnit("Write", Bytes(bytes))

  def collect(packets: Long): Future[Unit] = callUnit("Collect", UInt(packets))
  def discard(packets: Long): Future[Unit] = callUnit("Discard", UInt(packets))
  def clear(): Future[Unit] = callUnit("Clear")

  // MAC addresses
  def sourceMAC(mac: String): Future[String] = call("Source MAC", Str(mac)).map { _.getString }
  def destinationMAC(mac: String): Future[String] = call("Destination MAC", Str(mac)).map { _.getString }

  // filtering
  def requireSrc(mac: String): Future[String] = call("Require Source MAC", Str(mac)).map { _.getString }
  def rejectSrc(mac: String): Future[String] = call("Reject Source MAC", Str(mac)).map { _.getString }

  def requireDest(mac: String): Future[String] = call("Require Destination MAC", Str(mac)).map { _.getString }
  def rejectDest(mac: String): Future[String] = call("Reject Destination MAC", Str(mac)).map { _.getString }

  def requireLen(len: Long): Future[Unit] = callUnit("Require Length", UInt(len))
  def rejectLen(len: Long): Future[Unit] = callUnit("Reject Length", UInt(len))

  def requireType(protocol: Int): Future[Unit] = callUnit("Require Ether Type", Integer(protocol))
  def rejectType(protocol: Int): Future[Unit] = callUnit("Reject Ether Type", Integer(protocol))

  def requireContent(ofs: Long, bytes: Array[Byte]): Future[Unit] = callUnit("Require Content", UInt(ofs), Bytes(bytes))
  def rejectContent(ofs: Long, bytes: Array[Byte]): Future[Unit] = callUnit("Reject Content", UInt(ofs), Bytes(bytes))

  // triggering
  def sendTrigger(ctx: Context): Future[Unit] = callUnit("Send Trigger", ctx.toData)
  def awaitTriggers(nTriggers: Long): Future[Double] = call("Wait for Trigger", UInt(nTriggers)).map { _.getValue }
}

class EthernetServerProxy(cxn: Connection, name: String, context: Context = Context(0, 0))
extends ServerProxy(cxn, name, context) with EthernetServer { server =>
  import EthernetServerProxy._

  def packet(ctx: Context = context) = new Packet(this, ctx)
}

object EthernetServerProxy {
  class Packet(server: EthernetServerProxy, ctx: Context) extends PacketProxy(server, ctx) with EthernetServer
}

