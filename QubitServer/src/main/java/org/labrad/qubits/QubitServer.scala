package org.labrad.qubits

import java.util.{List => JList}
import org.labrad.AbstractServer
import org.labrad.RequestCallback
import org.labrad.Servers
import org.labrad.annotations.ServerInfo
import org.labrad.data.Context
import org.labrad.data.Data
import org.labrad.data.Request
import org.labrad.events.MessageEvent
import org.labrad.events.MessageListener
import org.labrad.qubits.resources.AdcBoard
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.Resources
import scala.collection.JavaConverters._

@ServerInfo(name = "Qubit Sequencer",
    doc = """Builds and Runs qubit sequences
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
            |Version 0.6.1.""")
class QubitServer extends AbstractServer {

  private var wiringContext: Context = _

  override def init(): Unit = {
    val cxn = getConnection()
    wiringContext = cxn.newContext()
    loadWiringConfiguration()
    // automatically reload the wiring configuration when it changes
    cxn.addMessageListener(new MessageListener() {
      override def messageReceived(e: MessageEvent): Unit = {
        if (e.getMessageID() == 55443322L) {
          val serverName = e.getData().getClusterAsList().get(1).getString()
          if (serverName == Constants.GHZ_DAC_SERVER) {
            println(s"Server connected: $serverName -- refreshing wiring.")
            try {
              Thread.sleep(1000)
            } catch {
              case e1: InterruptedException =>
                e1.printStackTrace()
            }
            loadWiringConfiguration()
          }
        }
        else if (e.getContext() == wiringContext) {
          wiringContext = getConnection().newContext()
          loadWiringConfiguration()
        }
      }
    })
    val req = startRegistryRequest()
    req.add("Notify on Change", Data.valueOf(wiringContext.getLow()),
        Data.valueOf(true))
    val req2 = Request.to("Manager", wiringContext)
    req2.add("Subscribe to Named Message", Data.valueOf("Server Connect"), Data.valueOf(55443322L),
        Data.valueOf(true))
    cxn.sendAndWait(req)
    cxn.sendAndWait(req2)
  }

  override def shutdown(): Unit = {
    println("Qubit sequencer shutting down.")
  }

  /**
   * Create a request for the registry
   */
  private def startRegistryRequest(): Request = {
    Request.to(Constants.REGISTRY_SERVER, wiringContext)
  }

  /**
   * Load the current wiring configuration from the registry.
   */
  def loadWiringConfiguration(): Unit = {
    println("Updating wiring configuration...")

    // load wiring configuration from the registry
    val req = startRegistryRequest()
    req.add("cd", Data.valueOf(Constants.WIRING_PATH),
        Data.valueOf(true)) // create the directory if needed
    val idx = req.addRecord("get", Data.valueOf(Constants.WIRING_KEY)) //,
    // Data.valueOf(Constants.WIRING_TYPE)); // no longer enforcing wiring type ==> FAIL!
    val ans = getConnection().sendAndWait(req)

    // create objects for all resources
    val resources = ans.get(idx).get(0).getClusterAsList()
    //List<Data> resources = ans.get(idx).get(0).getDataList()
    val fibers = ans.get(idx).get(1).getDataList()
    val microwaves = ans.get(idx).get(2).getDataList()
    Resources.updateWiring(resources, fibers, microwaves)

    println("Wiring configuration updated.")

    this.loadBuildProperties()
  }

  /**
   * we make a BuildLoader for every DAC/ADC board. we run them asynchronously to get build information
   * from both the FPGA server and the registry.
   * @author pomalley
   *
   */
  private class BuildLoader(myBoard: DacBoard) extends RequestCallback {

    private var gotBuildNumber = false

    def run(): Unit = {
      // build and send request to the FPGA server
      val req = Request.to(Constants.GHZ_DAC_SERVER, wiringContext)
      req.add("Select Device", Data.valueOf(myBoard.getName()))
      req.add("Build Number")

      // TODO: let's temporarily try doing this synchronously
      // to see if we can figure out why neither onSuccess or onFailure
      // is being called when the FPGA server is restarted.
      //getConnection().send(req, this);
      try {
        val resp = getConnection().sendAndWait(req)
        onSuccess(req, resp)
      } catch {
        case e: Exception =>
          onFailure(req, e)
      }

      //System.out.println("Sent request for board " + myBoard.getName());
      //System.out.println(req.getServerName() + " (" + req.getServerID() + ")");

    }

    override def onSuccess(request: Request, response: JList[Data]): Unit = {
      if (!gotBuildNumber) {
        // we got the build number from the FPGA server
        val buildNumber = response.get(1).getString()
        myBoard.setBuildNumber(buildNumber)
        println(s"Board ${myBoard.getName} has build number ${myBoard.getBuildNumber}")
        gotBuildNumber = true
        // send out a new packet to the registry to look up info on this build number
        sendRegistryRequest()
      } else {
        // we have the build details from the registry
        myBoard.loadProperties(response.get(1))
        println(s"Loaded build properties for board ${myBoard.getName}")
      }
    }

    override def onFailure(request: Request, cause: Throwable): Unit = {
      if (!gotBuildNumber) {
        // we failed to get the build number from the FPGA server
        println(s"Board ${myBoard.getName} failed to get build number: Using default build number (5 for DAC, 1 for ADC).")
        myBoard.setBuildNumber("-1")
        gotBuildNumber = true
        // send out a packet to the registry anyway to get the details
        sendRegistryRequest()
      } else {
        // we failed to get the build details from the registry
        println(s"Exception when looking up ADC/DAC build properties: ${cause.getMessage}. Using default values.")
        if (myBoard.isInstanceOf[AdcBoard])
          myBoard.loadProperties(Constants.DEFAULT_ADC_PROPERTIES_DATA)
        else
          myBoard.loadProperties(Constants.DEFAULT_DAC_PROPERTIES_DATA)
      }
    }

    private def sendRegistryRequest(): Unit = {
      val regReq = startRegistryRequest()
      regReq.add("cd", Data.valueOf(Constants.BUILD_INFO_PATH))
      var number = myBoard.getBuildNumber()
      if (number == "-1") {
        if (myBoard.isInstanceOf[AdcBoard])
          number = "1"
        else
          number = "5"
      }
      regReq.add("get", Data.valueOf(myBoard.getBuildType() + number))

      // TODO: synchronous as above
      //getConnection().send(regReq, this);
      try {
        val resp = getConnection().sendAndWait(regReq)
        onSuccess(regReq, resp)
      } catch {
        case e: Exception =>
          onFailure(regReq, e)
      }
    }
  }

  /**
   * Load the build properties for the ADC and DAC boards.
   */
  def loadBuildProperties(): Unit = {
    println("Load DAC/ADC build properties...")
    val current = Resources.getCurrent()
    val dacs = current.getAll(classOf[DacBoard])
    println(s"dacs.size() = ${dacs.size}")
    // make and start a request to do look up build numbers and properties for each board
    for (board <- dacs.asScala) {
      val bl = new BuildLoader(board)
      bl.run()
    }

    // check to see that we've set build properties
    while (dacs.size() > 0) {
      val it = dacs.iterator()
      while (it.hasNext) {
        if (it.next().havePropertiesLoaded())
          it.remove()
      }
      var n = 0
      if (dacs.size() > 0) {
        println(s"Waiting on ${dacs.size} boards...")
        try {
          Thread.sleep(1000)
          n += 1
          if (n > 30) {
            System.err.println("Timeout when waiting for board build number info!")
            dacs.clear()
          }
        } catch {
          case e: InterruptedException =>
            System.err.println("Error while waiting for DAC board info!")
            e.printStackTrace()
        }
      } else {
        println("All boards loaded.")
      }
    }
    println("DAC/ADC build properties loaded.")
  }
}

object QubitServer {
  /**
   * Run this server.
   */
  def main(args: Array[String]) {
    Servers.runServer(classOf[QubitServer], classOf[QubitContext], args)
  }
}
