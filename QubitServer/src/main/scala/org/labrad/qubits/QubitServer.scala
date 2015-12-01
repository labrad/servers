package org.labrad.qubits

import java.util.concurrent.atomic.AtomicReference
import org.labrad._
import org.labrad.data._
import org.labrad.events.MessageEvent
import org.labrad.events.MessageListener
import org.labrad.qubits.proxies.FpgaServerProxy
import org.labrad.qubits.resources.AdcBoard
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.Resources
import scala.concurrent.{Await, Future}
import scala.concurrent.duration._

class QubitServer extends Server[QubitServer, QubitContext] {

  val name = "Qubit Sequencer"
  val doc = """Builds and Runs qubit sequences
            |
            |This server is designed to help you build sequences to control the
            |numerous devices involved in a multi-qubit experiment.  In general,
            |this is complicated by the fact that the way the control sequence
            |is constructed depends on the wiring among all the various devices,
            |and by the fact that the sequence itself must be properly constructed
            |to ensure that all the boards run, stay in sync, and return timing
            |results as appropriate.
            |
            |Information about the wiring setup (which should not change very often)
            |is loaded from the registry at ['', 'Servers', 'Qubit Server', 'Wiring'].
            |Please do not modify this directly, but rather use the 'WiringEditor.py'
            |script to make changes.  The wiring information is reloaded whenever this
            |registry entry is changed.
            |
            |To build sequences, the setup is described as a list of devices, each
            |of which can have any number of channels.  These channels are one of a
            |small set of types, such as 'Iq' for microwaves or 'FastBias' for flux
            |or SQUID bias.  Many of the commands used to build up the sequence require
            |you to specify which channel or channels the command should affect.
            |Channels are identified either by a pair of strings
            |(<device name>, <channel name>), or a single string <device name>
            |if the device has only one channel of the type needed for the command.
            |
            |Version 0.7.1.""".stripMargin

  implicit def executionContext = cxn.executionContext

  private var mgr: ManagerServerProxy = _
  private var buildReg: RegistryServerProxy = _
  private var wiringReg: RegistryServerProxy = _
  private var fpgaServer: FpgaServerProxy = _
  private val resources = new AtomicReference[Resources]

  override def init(): Unit = {
    this.mgr = new ManagerServerProxy(cxn)
    this.buildReg = new RegistryServerProxy(cxn, context = cxn.newContext)
    this.wiringReg = new RegistryServerProxy(cxn, context = cxn.newContext)
    this.fpgaServer = new FpgaServerProxy(cxn, context = cxn.newContext)

    val wiringMsg = 11223344
    val buildInfoMsg = 11335577
    val serverConnectMsg = 55443322

    // automatically reload the wiring configuration when it changes
    cxn.addMessageListener {
      // wiring updated in registry
      case Message(src, ctx, `wiringMsg`, data) =>
        println(s"Registry wiring info updated -- reloading config.")
        reload()

      // fpga build info updated in registry
      case Message(src, ctx, `buildInfoMsg`, data) =>
        println(s"Registry build info updated -- reloading config.")
        reload()

      // Server Connect
      case Message(src, ctx, `serverConnectMsg`, Cluster(id, serverName)) =>
        if (serverName == Constants.GHZ_FPGA_SERVER) {
          println(s"Server connected: $serverName -- reloading config.")
          try {
            // wait to allow fpga autodetection
            // TODO: need a more robust mechanism here
            Thread.sleep(1000)
          } catch {
            case e1: InterruptedException =>
              e1.printStackTrace()
          }
          reload()
        }
    }

    val req = wiringReg.packet()
    req.cd(Constants.WIRING_PATH, true)
    req.notifyOnChange(wiringMsg, true)
    Await.result(req.send(), 1.minute)

    val req2 = buildReg.packet()
    req2.cd(Constants.BUILD_INFO_PATH, true)
    req2.notifyOnChange(buildInfoMsg, true)
    Await.result(req2.send(), 1.minute)

    val req3 = mgr.packet() // don't really care about context here
    req3.subscribeToNamedMessage("Server Connect", serverConnectMsg, true)
    Await.result(req3.send(), 1.minute)

    reload()
  }

  def newContext(context: Context): QubitContext = {
    new QubitContext(cxn, () => resources.get())
  }

  override def shutdown(): Unit = {
    println("Qubit sequencer shutting down.")
  }

  /**
   * Load the current wiring configuration from the registry.
   */
  def loadWiringConfiguration(): Future[(Seq[Data], Seq[Data], Seq[Data])] = {
    // load wiring configuration from the registry
    val req = wiringReg.packet()
    req.cd(Constants.WIRING_PATH, true) // create the directory if needed
    val wiringFuture = req.get(Constants.WIRING_KEY) // cannot enforce wiring type, because it includes variable-length clusters
    req.send()

    wiringFuture.map { wiring =>
      val Cluster(resources @ _*) = wiring(0)
      val fibers = wiring(1).get[Seq[Data]]
      val microwaves = wiring(2).get[Seq[Data]]
      (resources, fibers, microwaves)
    }
  }

  /**
   * Load build number for all connected ADC and DAC fpga boards.
   *
   * Returns two maps, the first from ADC device name to build number, and the
   * second from DAC device name to build number. If the build number cannot be
   * determined for a given board, that board will not be included in the
   * result.
   */
  def loadBuildNumbers(): Future[(Map[String, String], Map[String, String])] = {
    val adcBuildNumsF = fpgaServer.listADCs().flatMap { adcs =>
      loadBuildNumbers(adcs)
    }
    val dacBuildNumsF = fpgaServer.listDACs().flatMap { dacs =>
      loadBuildNumbers(dacs)
    }

    for {
      adcBuildNums <- adcBuildNumsF
      dacBuildNums <- dacBuildNumsF
    } yield (adcBuildNums, dacBuildNums)
  }

  def loadBuildNumbers(boards: Seq[String]): Future[Map[String, String]] = {
    val reqs = boards.map { board =>
      loadBuildNumber(board).map { buildOpt =>
        buildOpt.map(build => board -> build)
      }
    }

    Future.sequence(reqs).map { results =>
      results.flatten.toMap
    }
  }

  def loadBuildNumber(board: String): Future[Option[String]] = {
    val p = fpgaServer.packet()
    p.selectDevice(board)
    val f = p.buildNumber()
    p.send()

    f.map { build =>
      Some(build)
    }.recover {
      case e: Exception =>
        None
    }
  }

  /**
   * Load build properties from the registry for all known ADC and DAC builds.
   *
   * Returns a Future that will fire with a map from build name to build
   * properties for that build, where the build properties are given as a map
   * from string property name to long value.
   */
  def loadBuildProperties(): Future[(Map[String, Map[String, Long]], Map[String, Map[String, Long]])] = {
    val adcBuildPropsF = loadBuildProperties(Constants.BUILD_INFO_ADC_PREFIX)
    val dacBuildPropsF = loadBuildProperties(Constants.BUILD_INFO_DAC_PREFIX)

    for {
      adcBuildProps <- adcBuildPropsF
      dacBuildProps <- dacBuildPropsF
    } yield (adcBuildProps, dacBuildProps)
  }

  def loadBuildProperties(prefix: String): Future[Map[String, Map[String, Long]]] = {
    val p = buildReg.packet()
    p.cd(Constants.BUILD_INFO_PATH)
    val f = p.dir()
    p.send()

    f.flatMap { case (dirs, keys) =>
      val buildInfoKeys = keys.filter(_.startsWith(prefix))
      val p = buildReg.packet()
      val fs = buildInfoKeys.map { key =>
        p.get(key).map { value =>
          val props = value.get[Seq[(String, Long)]].toMap
          key -> props
        }
      }
      p.send()

      Future.sequence(fs).map(_.toMap)
    }
  }

  def reload(): Unit = {
    val wiringF = loadWiringConfiguration()
    val buildNumsF = loadBuildNumbers()
    val buildPropsF = loadBuildProperties()

    val f = for {
      (resources, fibers, microwaves) <- wiringF
      (adcNums, dacNums) <- buildNumsF
      (adcProps, dacProps) <- buildPropsF
    } yield {
      Resources.create(resources, fibers, microwaves, adcNums, dacNums, adcProps, dacProps)
    }

    val newResources = Await.result(f, 1.minute)
    resources.set(newResources)
    println("DAC/ADC build properties loaded.")
  }
}

object QubitServer {
  /**
   * Run this server.
   */
  def main(args: Array[String]) {
    val server = new QubitServer
    Server.run(server, args)
  }
}
