package org.labrad.ethernet.server

import org.labrad._
import org.labrad.ethernet.client.EthernetServerProxy
import org.labrad.ethernet.server.TestUtils._
import org.pcap4j.core.Pcaps
import org.pcap4j.util.MacAddress
import org.scalatest.{FunSuite, Matchers, Tag}
import scala.concurrent.ExecutionContext.Implicits.global
import scala.concurrent.duration._

class EthernetServerTest extends FunSuite with Matchers {
  def findServer(c: Connection): EthernetServerProxy = {
    val mgr = new ManagerServerProxy(c)

    val servers = await(mgr.servers())
    val names = servers.collect { case (_, name) if name.endsWith("Direct Ethernet") => name }
    assert(names.length == 1, s"expected one direct ethernet server. found: ${names.mkString(",")}")
    val name = names.head

    new EthernetServerProxy(c, name)
  }

  test("ethernet server starts up") {
    withManager { (host, port, password) =>
      withServer(host, port, password) {
        withClient(host, port, password) { c =>
          val de = findServer(c)

          val adapters = await(de.adapters()).map(_._2)
          val adapter = adapters(0)

          val device = Pcaps.getDevByName(adapter)
          val bus = new EthernetBus(device)

          val dst = bus.macs.headOption.getOrElse(MacAddress.getByName("00:11:22:33:44:55"))
          val src = MacAddress.getByName("00:11:22:33:44:FF")

          await(de.connect(adapter))
          await(de.timeout(1.seconds))
          await(de.requireSrc(src.toString))
          await(de.requireDest(dst.toString))
          await(de.listen())

          an[Exception] should be thrownBy {
            await(de.collect(1))
          }

          val data = Array.tabulate[Byte](256) { i => i.toByte }
          val f = de.collect(1)
          bus.send(RawEthernet(src = src, dst = dst, data = data))
          await(f)

          val pkts = await(de.read(1))
          assert(pkts.length == 1)
          pkts.head match {
            case (srcMac, dstMac, etherType, pktData) =>
              assert(MacAddress.getByName(srcMac) == src)
              assert(MacAddress.getByName(dstMac) == dst)
              assert(etherType == pktData.length)
              assert(pktData.toSeq == data.toSeq)
          }
        }
      }
    }
  }

  test("contexts wait for triggers") {
    withManager { (host, port, password) =>
      withServer(host, port, password) {
        withClient(host, port, password) { c =>
          val de = findServer(c)
          val de1 = new EthernetServerProxy(c, de.name, c.newContext)
          val de2 = new EthernetServerProxy(c, de.name, c.newContext)
          val de3 = new EthernetServerProxy(c, de.name, c.newContext)
          val triggerContext = de.context.copy(high = c.id)

          val f = de1.awaitTriggers(2)

          Thread.sleep(1000)
          de2.sendTrigger(triggerContext)

          Thread.sleep(1000)
          de3.sendTrigger(triggerContext)

          val t = await(f, timeout = 1.seconds) // should return very quickly
          assert(t > 1.9) // total wait should have been about two seconds
          assert(t < 2.5)

          // can send triggers in advance
          await(de2.sendTrigger(triggerContext))
          await(de3.sendTrigger(triggerContext))
          val t2 = await(de1.awaitTriggers(2), timeout = 1.seconds)
          assert(t2 == 0) // triggers arrived before the wait request

          // can send some triggers in advance, some later
          await(de2.sendTrigger(triggerContext))
          val f3 = de1.awaitTriggers(2)

          Thread.sleep(1000)
          await(de3.sendTrigger(triggerContext))
          val t3 = await(f3, timeout = 1.seconds)
          assert(t3 > 0.9) // should have taken about one second
          assert(t3 < 1.5)
        }
      }
    }
  }
}
