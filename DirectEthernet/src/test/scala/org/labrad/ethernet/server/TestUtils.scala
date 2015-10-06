package org.labrad.ethernet.server

import java.io.File
import java.nio.ByteOrder
import java.util.Date
import org.labrad._
import org.labrad.data._
import org.labrad.manager.CentralNode
import org.labrad.registry._
import org.labrad.types._
import org.labrad.util.{Logging, Util}
import org.scalatest.FunSuite
import scala.concurrent.{Await, Future}
import scala.concurrent.duration._
import scala.util.Random

object TestUtils extends {

  def await[A](future: Future[A], timeout: Duration = 30.seconds): A = Await.result(future, timeout)

  def withManager[T](f: (String, Int, Array[Char]) => T): T = {
    val host = "localhost"
    val port = 10000 + Random.nextInt(50000)
    val password = "testPassword12345!@#$%".toCharArray

    val registryFile = File.createTempFile("labrad-registry", "")
    val registryStore = SQLiteStore(registryFile)

    val manager = new CentralNode(port, password, Some(registryStore))
    try {
      f(host, port, password)
    } finally {
      manager.stop()
    }
  }

  def withClient(host: String, port: Int, password: Array[Char])(func: Client => Unit) = {
    val c = new Client(host = host, port = port, password = password)
    c.connect()
    try {
      func(c)
    } finally {
      try c.close() catch { case _: Throwable => }
    }
  }

  def withServer[T](host: String, port: Int, password: Array[Char])(body: => T) = {
    val server = new DirectEthernet
    server.start(host, port, password, nameOpt = Some("Test Direct Ethernet"))
    try {
      body
    } finally {
      try server.stop() catch { case _: Throwable => }
    }
  }
}
