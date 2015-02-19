package org.labrad.qubits.proxies

import org.labrad._
import org.labrad.data._
import scala.concurrent.{ExecutionContext, Future}

trait FpgaServer extends Requester {
  def listDACs(): Future[Seq[String]] =
    call("List DACs").map { _.get[Seq[String]] }

  def listADCs(): Future[Seq[String]] =
    call("List ADCs").map { _.get[Seq[String]] }

  def selectDevice(dev: String): Future[Unit] =
    callUnit("Select Device", Str(dev))

  def buildNumber(): Future[String] =
    call("Build Number").map { _.get[String] }
}

class FpgaServerProxy(cxn: Connection, name: String = "GHz FPGAs", context: Context = Context(0, 0))
    extends ServerProxy(cxn, name, context) with FpgaServer {
  def packet(ctx: Context = context) = new FpgaServerPacket(this, ctx)
}

class FpgaServerPacket(server: ServerProxy, ctx: Context)
  extends PacketProxy(server, ctx) with FpgaServer
