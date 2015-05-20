package org.labrad.qubits

import com.google.common.collect.ListMultimap
import com.google.common.collect.Lists
import com.google.common.collect.Maps
import com.google.common.collect.Sets
import java.util.ArrayList
import java.util.List
import java.util.Map
import java.util.Set
import org.labrad.data.Data
import org.labrad.qubits.channels._
import org.labrad.qubits.enums.DacTriggerId
import org.labrad.qubits.mem.MemoryCommand
import org.labrad.qubits.resources.AdcBoard
import org.labrad.qubits.resources.AnalogBoard
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.MicrowaveBoard
import scala.collection.JavaConverters._


/**
 * "Experiment holds all the information about the fpga sequence as it is being built,
 * and knows how to produce the memory and sram instructions that actually get sent out to run the sequence."
 *
 * For the ADC addition, we now have to be careful to only perform things like memory ops on DAC FpgaModels, not ADC ones.
 *
 * @author maffoo
 * @author pomalley
 */
class Experiment(devices: List[Device]) {

  private val devicesByName: Map[String, Device] = Maps.newHashMap()
  private val fpgas: Set[FpgaModel] = Sets.newHashSet()
  private val timerFpgas: Set[FpgaModelDac] = Sets.newHashSet()
  private val nonTimerFpgas: Set[FpgaModelDac] = Sets.newHashSet()

  private val setupPackets: List[Data] = Lists.newArrayList()
  private val setupState: List[String] = Lists.newArrayList()
  private var timingOrder: List[TimingOrderItem] = null
  private var autoTriggerId: DacTriggerId = null
  private var autoTriggerLen = 0

  private var loopDelay: Double = 0
  private var loopDelayConfigured = false

  for (dev <- devices.asScala) {
    devicesByName.put(dev.getName(), dev)
  }

  createResourceModels()

  //
  // Resources
  //

  private def createResourceModels(): Unit = {
    val boards: Map[DacBoard, FpgaModel] = Maps.newHashMap()

    // build models for all required resources
    for (ch <- getChannels(classOf[FpgaChannel]).asScala) {
      val board = ch.getDacBoard()
      var fpga = boards.get(board)
      if (fpga == null) {
        fpga = board match {
          case board: AnalogBoard => new FpgaModelAnalog(board, this)
          case board: MicrowaveBoard => new FpgaModelMicrowave(board, this)
          case board: AdcBoard => new FpgaModelAdc(board, this)
          case _ => sys.error(s"Unknown DAC board type for board ${board.getName}")
        }
        boards.put(board, fpga)
        fpgas.add(fpga)
      }
      // connect this channel to the experiment and fpga model
      ch.setExperiment(this)
      ch.setFpgaModel(fpga)
    }

    for (ch <- getChannels(classOf[FastBiasSerialChannel]).asScala) {
      // TODO: how to represent DC rack hardware in the experiment?
    }

    // build lists of FPGA boards that have or don't have a timing channel
    nonTimerFpgas.addAll(getDacFpgas())
    for (ch <- getChannels(classOf[PreampChannel]).asScala) {
      val fpga = ch.getFpgaModel()
      timerFpgas.add(fpga)
      nonTimerFpgas.remove(fpga)
    }
  }


  //
  // Devices
  //

  def getDevice(name: String): Device = {
    require(devicesByName.containsKey(name), s"Device '$name' not found.")
    devicesByName.get(name)
  }

  private def getDevices(): List[Device] = {
    devices
  }

  def getChannels(): List[Channel] = {
    getChannels(classOf[Channel])
  }

  def getChannels[T <: Channel](cls: Class[T]): List[T] = {
    val channels: List[T] = Lists.newArrayList()
    for (dev <- devices.asScala) {
      channels.addAll(dev.getChannels(cls))
    }
    channels
  }


  //
  // FPGAs
  //

  /**
   * Clear the memory or jump table commands for these FPGAs.
   */
  def clearControllers(): Unit = {
    for (fpga <- getDacFpgas().asScala) {
      fpga.clearController()
    }
  }

  /**
   * Get a list of FPGAs involved in this experiment
   */
  def getFpgas(): Set[FpgaModel] = {
    Sets.newHashSet(fpgas)
  }

  def getTimerFpgas(): Set[FpgaModelDac] = {
    Sets.newHashSet(timerFpgas)
  }

  def getNonTimerFpgas(): Set[FpgaModelDac] = {
    Sets.newHashSet(nonTimerFpgas)
  }

  def getMicrowaveFpgas(): Set[FpgaModelMicrowave] = {
    val fpgas: Set[FpgaModelMicrowave] = Sets.newHashSet()
    for (fpga <- this.fpgas.asScala) {
      if (fpga.isInstanceOf[FpgaModelMicrowave]) {
        fpgas.add(fpga.asInstanceOf[FpgaModelMicrowave])
      }
    }
    fpgas
  }

  /**
   * Many operations are only performed on DAC fpgas.
   * @return A set of all FpgaModelDac's in this experiment.
   * @author pomalley
   */
  def getDacFpgas(): Set[FpgaModelDac] = {
    val fpgas: Set[FpgaModelDac] = Sets.newHashSet()
    for (fpga <- this.fpgas.asScala) {
      if (fpga.isInstanceOf[FpgaModelDac]) {
        fpgas.add(fpga.asInstanceOf[FpgaModelDac])
      }
    }
    fpgas
  }

  /**
   * Conversely, sometimes we need the ADC fpgas.
   * @return A set of all FpgaModelAdc's in this experiment.
   * @author pomalley
   */
  def getAdcFpgas(): Set[FpgaModelAdc] = {
    val fpgas: Set[FpgaModelAdc] = Sets.newHashSet()
    for (fpga <- this.fpgas.asScala) {
      if (fpga.isInstanceOf[FpgaModelAdc]) {
        fpgas.add(fpga.asInstanceOf[FpgaModelAdc])
      }
    }
    fpgas
  }

  def getFpgaNames(): List[String] = {
    val boardsToRun: List[String] = Lists.newArrayList()
    for (fpga <- fpgas.asScala) {
      boardsToRun.add(fpga.getName())
    }
    boardsToRun
  }

  /**
   * Clear all configuration that has been set for this experiment
   */
  def clearConfig(): Unit = {
    // reset setup packets
    clearSetupState()

    // clear timing order
    timingOrder = null

    // clear autotrigger
    autoTriggerId = null

    // clear configuration on all channels
    for (dev <- getDevices().asScala) {
      for (ch <- dev.getChannels().asScala) {
        ch.clearConfig()
      }
    }

    // de-configure loopDelay
    loopDelayConfigured = false
  }


  private def clearSetupState(): Unit = {
    setupState.clear()
    setupPackets.clear()
  }

  def setSetupState(state: List[String], packets: List[Data]): Unit = {
    clearSetupState()
    setupState.addAll(state)
    setupPackets.addAll(packets)
  }

  def getSetupState(): List[String] = {
    Lists.newArrayList(setupState)
  }

  def getSetupPackets(): List[Data] = {
    Lists.newArrayList(setupPackets)
  }

  def setAutoTrigger(id: DacTriggerId, length: Int): Unit = {
    autoTriggerId = id
    autoTriggerLen = length
  }

  def getAutoTriggerId(): DacTriggerId = {
    autoTriggerId
  }

  def getAutoTriggerLen(): Int = {
    autoTriggerLen
  }

  def setTimingOrder(to: List[TimingOrderItem]): Unit = {
    timingOrder = new ArrayList[TimingOrderItem](to)
  }

  def configLoopDelay(loopDelay: Double): Unit = {
    this.loopDelay = loopDelay
    this.loopDelayConfigured = true
  }

  def isLoopDelayConfigured(): Boolean = {
    loopDelayConfigured
  }
  def getLoopDelay(): Double = {
    loopDelay
  }

  /**
   * Get the order of boards from which to return timing data
   * @return
   */
  def getTimingOrder(): List[String] = {
    val order: List[String] = Lists.newArrayList()
    for (toi <- getTimingChannels().asScala) {
      order.add(toi.toString())
    }
    order
  }

  def getTimingChannels(): List[TimingOrderItem] = {
    // if we have an existing timing order, use it
    if (timingOrder != null)
      timingOrder
    // if not, use everything--all DACs, all ADCs/active ADC channels
    else {
      val to: List[TimingOrderItem] = Lists.newArrayList()
      for (t <- getChannels(classOf[TimingChannel]).asScala) {
        t match {
          case t: AdcChannel => to.add(new TimingOrderItem(t, t.getDemodChannel()))
          case t => new TimingOrderItem(t)
        }
      }
      to
    }
  }

  def adcTimingOrderIndices(): List[Int] = {
    val list: List[Int] = Lists.newArrayList()
    for ((toi, i) <- getTimingChannels().asScala.zipWithIndex) {
      if (toi.isAdc())
        list.add(i)
    }
    list
  }
  def dacTimingOrderIndices(): List[Int] = {
    val list: List[Int] = Lists.newArrayList()
    for ((toi, i) <- getTimingChannels().asScala.zipWithIndex) {
      if (!(toi.isAdc()))
        list.add(i)
    }
    list
  }

  //
  // Jump Table
  //

  def addJumpTableEntry(commandName: String, commandData: Data): Unit = {
    for (fpga <- getDacFpgas().asScala) {
      fpga.getJumpTableController().addJumpTableEntry(commandName, commandData)
    }
  }


  //
  // Memory
  //

  /**
   * Add bias commands to a set of FPGA boards. Only applies to DACs.
   * @param allCmds
   */
  def addBiasCommands(allCmds: ListMultimap[FpgaModelDac, MemoryCommand], delay: Double): Unit = {
    // find the maximum number of commands on any single fpga board
    var maxCmds = 0
    for (fpga <- allCmds.keySet().asScala) {
      maxCmds = Math.max(maxCmds, allCmds.get(fpga).size())
    }

    // add commands for each board, including noop padding and final delay
    for (fpga <- getDacFpgas().asScala) {
      val cmds = allCmds.get(fpga)
      if (cmds != null) {
        fpga.getMemoryController.addMemoryCommands(cmds)
        fpga.getMemoryController.addMemoryNoops(maxCmds - cmds.size())
      } else {
        fpga.getMemoryController.addMemoryNoops(maxCmds)
      }
      if (delay > 0) {
        fpga.getMemoryController.addMemoryDelay(delay)
      }
    }
  }

  /**
   * Add a delay command to exactly one board
   *
   */
  def addSingleMemoryDelay(fpga: FpgaModelDac, delay_us: Double): Unit = {
    fpga.getMemoryController.addMemoryDelay(delay_us)
  }

  /**
   * Add a delay in the memory sequence of all boards.
   * Only applies to DACs.
   */
  def addMemoryDelay(microseconds: Double): Unit = {
    for (fpga <- getDacFpgas().asScala) {
      fpga.getMemoryController.addMemoryDelay(microseconds)
    }
  }

  def addMemSyncDelay(): Unit = {
    //Find maximum sequence length on all fpgas
    var maxT_us = 0.0
    for (fpga <- getFpgas().asScala) {
      try {
        val t_us = fpga.getSequenceLengthPostSRAM_us()
        maxT_us = Math.max(maxT_us, t_us)
      } catch {
        case ex: java.lang.IllegalArgumentException =>
      }
    }

    for (fpga <- getDacFpgas().asScala) {
      var t = 0.0
      try {
        t = fpga.getSequenceLength_us()
      } catch {
        case ex: java.lang.IllegalArgumentException =>
      }
      if (t < maxT_us) {
        fpga.getMemoryController.addMemoryDelay(maxT_us - t)
      } else {
        fpga.getMemoryController.addMemoryNoop()
      }
    }
  }

  /**
   * Call SRAM. Only applies to DACs.
   */
  def callSramBlock(block: String): Unit = {
    for (fpga <- getDacFpgas().asScala) {
      fpga.getMemoryController.callSramBlock(block)
    }
  }

  def callSramDualBlock(block1: String, block2: String): Unit = {
    for (fpga <- getDacFpgas().asScala) {
      fpga.getMemoryController.callSramDualBlock(block1, block2)
    }
  }

  def setSramDualBlockDelay(delay_ns: Double): Unit = {
    for (fpga <- getDacFpgas().asScala) {
      fpga.getMemoryController.setSramDualBlockDelay(delay_ns)
    }
  }

  /**
   * Get the length of the shortest SRAM block across all fpgas.
   * @return
   */
  def getShortestSram(): Int = {
    var i = 0
    for (fpga <- getDacFpgas().asScala) {
      for (block <- fpga.getBlockNames().asScala) {
        val len = fpga.getBlockLength(block)
        if (i == 0 || len < i) {
          i = len
        }
      }
    }
    i
  }

  /**
   * Start timer on a set of boards.
   * This only applies to DAC fpgas.
   */
  def startTimer(channels: List[PreampChannel]): Unit = {
    val starts: Set[FpgaModelDac] = Sets.newHashSet()
    val noops: Set[FpgaModelDac] = getTimerFpgas()
    for (ch <- channels.asScala) {
      val fpga = ch.getFpgaModel()
      starts.add(fpga)
      noops.remove(fpga)
    }
    // non-timer boards get started if they have never been started before
    for (fpga <- getNonTimerFpgas().asScala) {
      if (!fpga.getMemoryController.isTimerStarted()) {
        starts.add(fpga)
      } else {
        noops.add(fpga)
      }
    }
    // start the timer on requested boards
    for (fpga <- starts.asScala) {
      fpga.getMemoryController.startTimer()
    }
    // insert a no-op on all other boards
    for (fpga <- noops.asScala) {
      fpga.getMemoryController.addMemoryNoop()
    }
  }

  /**
   * Stop timer on a set of boards.
   */
  def stopTimer(channels: List[PreampChannel]): Unit = {
    val stops: Set[FpgaModelDac] = Sets.newHashSet()
    val noops: Set[FpgaModelDac] = getTimerFpgas()
    for (ch <- channels.asScala) {
      val fpga = ch.getFpgaModel()
      stops.add(fpga)
      noops.remove(fpga)
    }
    // stop non-timer boards if they are currently running
    for (fpga <- getNonTimerFpgas().asScala) {
      if (fpga.getMemoryController.isTimerRunning()) {
        stops.add(fpga)
      } else {
        noops.add(fpga)
      }
    }
    // stop the timer on requested boards and non-timer boards
    for (fpga <- stops.asScala) {
      fpga.getMemoryController.stopTimer()
    }
    // insert a no-op on all other boards
    for (fpga <- noops.asScala) {
      fpga.getMemoryController.addMemoryNoop()
    }
  }

}

// stupid handler class to implement a timing order item
class TimingOrderItem(channel: TimingChannel, subChannel: Int = -1) {

  override def toString(): String = {
    if (subChannel == -1)
      channel.getDacBoard.getName
    else
      channel.getDacBoard.getName + "::" + subChannel
  }

  def isAdc(): Boolean = {
    channel.isInstanceOf[AdcChannel]
  }

  /**
   * @param data Must be *w (DACs) or (*i{I}, *i{Q}) (ADCs)
   * @return T/F for 1/0 qubit state for each item in data.
   */
  def interpretData(data: Data): Array[Boolean] = {
    if (isAdc()) {
      require(data.matchesType("(*i, *i)"),
          s"interpretData called with data type ${data.getType} on an ADC channel. Qubit Sequencer mixup.")
      channel.asInstanceOf[AdcChannel].interpretPhases(data.get(0).getIntArray(), data.get(1).getIntArray())
    } else {
      require(data.matchesType("*w"),
          s"interpretData called with data type ${data.getType} on a DAC channel. Qubit Sequencer mixup.")
      channel.asInstanceOf[PreampChannel].interpretSwitches(data.getWordArray())
    }
  }

  def getChannel(): TimingChannel = {
    channel
  }
}
