package org.labrad.qubits

import org.labrad.data.Data
import org.labrad.qubits.channels._
import org.labrad.qubits.enums.DacTriggerId
import org.labrad.qubits.mem.MemoryCommand
import org.labrad.qubits.resources.AdcBoard
import org.labrad.qubits.resources.AnalogBoard
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.MicrowaveBoard
import org.labrad.types._
import scala.collection.mutable
import scala.reflect.ClassTag

/**
 * "Experiment holds all the information about the fpga sequence as it is being built,
 * and knows how to produce the memory and sram instructions that actually get sent out to run the sequence."
 *
 * For the ADC addition, we now have to be careful to only perform things like memory ops on DAC FpgaModels, not ADC ones.
 *
 * @author maffoo
 * @author pomalley
 */
class Experiment(val devices: Seq[Device]) {

  private val devicesByName = devices.map { dev =>
    dev.name -> dev
  }.toMap

  private val boards = mutable.Map.empty[DacBoard, FpgaModel]

  // build models for all required resources
  for (ch <- getChannels[FpgaChannel]) {
    val board = ch.dacBoard
    val fpga = boards.getOrElseUpdate(board, {
      board match {
        case board: AnalogBoard => new FpgaModelAnalog(board, this)
        case board: MicrowaveBoard => new FpgaModelMicrowave(board, this)
        case board: AdcBoard => new FpgaModelAdc(board, this)
        case _ => sys.error(s"Unknown DAC board type for board ${board.name}")
      }
    })
    // connect this channel to the experiment and fpga model
    ch.setExperiment(this)
    ch.setFpgaModel(fpga)
  }

  for (ch <- getChannels[FastBiasSerialChannel]) {
    // TODO: how to represent DC rack hardware in the experiment?
  }

  private val fpgas = boards.values.toSet

  // build sets of FPGA boards that have or don't have a timing channel
  private val timerFpgas = getChannels[PreampChannel].map(_.getFpgaModel).toSet
  private val nonTimerFpgas = getDacFpgas() -- timerFpgas


  private val setupPackets = mutable.Buffer.empty[Data]
  private val setupState = mutable.Buffer.empty[String]
  private var timingOrder: Seq[TimingOrderItem] = null
  private var autoTriggerId: DacTriggerId = null
  private var autoTriggerLen = 0

  private var loopDelay: Double = 0
  private var loopDelayConfigured = false

  //
  // Devices
  //

  def getDevice(name: String): Device = {
    devicesByName.get(name).getOrElse {
      sys.error(s"Device '$name' not found.")
    }
  }

  private def getDevices(): Seq[Device] = {
    devices
  }

  def getChannels(): Seq[Channel] = {
    getChannels[Channel]
  }

  def getChannels[T <: Channel : ClassTag]: Seq[T] = {
    devices.flatMap(_.getChannels[T])
  }


  //
  // FPGAs
  //

  /**
   * Clear the memory or jump table commands for these FPGAs.
   */
  def clearControllers(): Unit = {
    for (fpga <- getDacFpgas()) {
      fpga.clearController()
    }
  }

  /**
   * Get a list of FPGAs involved in this experiment
   */
  def getFpgas(): Set[FpgaModel] = fpgas
  def getTimerFpgas(): Set[FpgaModelDac] = timerFpgas
  def getNonTimerFpgas(): Set[FpgaModelDac] = nonTimerFpgas

  def getMicrowaveFpgas(): Set[FpgaModelMicrowave] = {
    fpgas.collect { case fpga: FpgaModelMicrowave => fpga }
  }

  /**
   * Many operations are only performed on DAC fpgas.
   * @return A set of all FpgaModelDac's in this experiment.
   * @author pomalley
   */
  def getDacFpgas(): Set[FpgaModelDac] = {
    fpgas.collect { case dac: FpgaModelDac => dac }
  }

  /**
   * Conversely, sometimes we need the ADC fpgas.
   * @return A set of all FpgaModelAdc's in this experiment.
   * @author pomalley
   */
  def getAdcFpgas(): Set[FpgaModelAdc] = {
    fpgas.collect { case adc: FpgaModelAdc => adc }
  }

  def getFpgaNames(): Seq[String] = {
    fpgas.map(_.name).toSeq
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
    for {
      dev <- getDevices()
      ch <- dev.getChannels()
    } {
      ch.clearConfig()
    }

    // de-configure loopDelay
    loopDelayConfigured = false
  }


  private def clearSetupState(): Unit = {
    setupState.clear()
    setupPackets.clear()
  }

  def setSetupState(state: Seq[String], packets: Seq[Data]): Unit = {
    clearSetupState()
    setupState ++= state
    setupPackets ++= packets
  }

  def getSetupState(): Seq[String] = {
    setupState.toVector
  }

  def getSetupPackets(): Seq[Data] = {
    setupPackets.toVector
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

  def setTimingOrder(to: Seq[TimingOrderItem]): Unit = {
    timingOrder = to
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
  def getTimingOrder(): Seq[String] = {
    getTimingChannels.map(_.toString)
  }

  def getTimingChannels(): Seq[TimingOrderItem] = {
    // if we have an existing timing order, use it
    if (timingOrder != null) {
      timingOrder
    // if not, use everything--all DACs, all ADCs/active ADC channels
    } else {
      getChannels[TimingChannel].map {
        case t: AdcChannel => new TimingOrderItem(t, t.demodChannel)
        case t => new TimingOrderItem(t)
      }
    }
  }

  def adcTimingOrderIndices(): Seq[Int] = {
    getTimingChannels.zipWithIndex.collect {
      case (toi, i) if toi.isAdc => i
    }
  }

  def dacTimingOrderIndices(): Seq[Int] = {
    getTimingChannels.zipWithIndex.collect {
      case (toi, i) if !toi.isAdc => i
    }
  }

  //
  // Jump Table
  //

  def addJumpTableEntry(commandName: String, commandData: Data): Unit = {
    for (fpga <- getDacFpgas) {
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
  def addBiasCommands(allCmds: Map[FpgaModelDac, Seq[MemoryCommand]], delay: Double): Unit = {
    // find the maximum number of commands on any single fpga board
    var maxCmds = 0
    for ((fpga, cmds) <- allCmds) {
      maxCmds = Math.max(maxCmds, cmds.size)
    }

    // add commands for each board, including noop padding and final delay
    for (fpga <- getDacFpgas) {
      allCmds.get(fpga) match {
        case Some(cmds) =>
          fpga.getMemoryController.addMemoryCommands(cmds)
          fpga.getMemoryController.addMemoryNoops(maxCmds - cmds.size)

        case None =>
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
    for (fpga <- getDacFpgas) {
      fpga.getMemoryController.addMemoryDelay(microseconds)
    }
  }

  def addMemSyncDelay(): Unit = {
    //Find maximum sequence length on all fpgas
    var maxT_us = 0.0
    for (fpga <- getFpgas) {
      try {
        val t_us = fpga.getSequenceLengthPostSRAM_us()
        maxT_us = Math.max(maxT_us, t_us)
      } catch {
        case ex: java.lang.IllegalArgumentException =>
      }
    }

    for (fpga <- getDacFpgas) {
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
    for (fpga <- getDacFpgas) {
      fpga.getMemoryController.callSramBlock(block)
    }
  }

  def callSramDualBlock(block1: String, block2: String): Unit = {
    for (fpga <- getDacFpgas) {
      fpga.getMemoryController.callSramDualBlock(block1, block2)
    }
  }

  def setSramDualBlockDelay(delay_ns: Double): Unit = {
    for (fpga <- getDacFpgas) {
      fpga.getMemoryController.setSramDualBlockDelay(delay_ns)
    }
  }

  /**
   * Get the length of the shortest SRAM block across all fpgas.
   * @return
   */
  def getShortestSram(): Int = {
    val lens = for {
      fpga <- getDacFpgas()
      block <- fpga.getBlockNames()
    } yield fpga.getBlockLength(block)

    if (lens.isEmpty) 0 else lens.min
  }

  /**
   * Start timer on a set of boards.
   * This only applies to DAC fpgas.
   */
  def startTimer(channels: Seq[PreampChannel]): Unit = {
    val boards = channels.map(_.getFpgaModel).toSet

    // start requested timers
    val timerStarts = boards
    val timerNoops = getTimerFpgas -- boards

    // start non timer boards that have never been started
    val (nonTimerNoops, nonTimerStarts) = getNonTimerFpgas.partition(_.getMemoryController.isTimerStarted)

    // start the timer on requested boards
    for (fpga <- timerStarts ++ nonTimerStarts) {
      fpga.getMemoryController.startTimer()
    }
    // insert a no-op on all other boards
    for (fpga <- timerNoops ++ nonTimerNoops) {
      fpga.getMemoryController.addMemoryNoop()
    }
  }

  /**
   * Stop timer on a set of boards.
   */
  def stopTimer(channels: Seq[PreampChannel]): Unit = {
    val boards = channels.map(_.getFpgaModel).toSet

    // stop requested timers
    val timerStops = boards
    val timerNoops = getTimerFpgas -- boards

    // stop non-timer boards if they are currently running
    val (nonTimerStops, nonTimerNoops) = getNonTimerFpgas.partition(_.getMemoryController.isTimerRunning)

    // stop the timer on requested boards and non-timer boards
    for (fpga <- timerStops ++ nonTimerStops) {
      fpga.getMemoryController.stopTimer()
    }
    // insert a no-op on all other boards
    for (fpga <- timerNoops ++ nonTimerNoops) {
      fpga.getMemoryController.addMemoryNoop()
    }
  }

}

// stupid handler class to implement a timing order item
class TimingOrderItem(channel: TimingChannel, subChannel: Int = -1) {

  override def toString(): String = {
    if (subChannel == -1)
      channel.dacBoard.name
    else
      channel.dacBoard.name + "::" + subChannel
  }

  def isAdc(): Boolean = {
    channel.isInstanceOf[AdcChannel]
  }

  /**
   * @param data Must be *w (DACs) or (*i{I}, *i{Q}) (ADCs)
   * @return T/F for 1/0 qubit state for each item in data.
   */
  def interpretData(data: Data): Array[Boolean] = {
    channel match {
      case adc: AdcChannel =>
        require(data.t == Type("(*i, *i)"),
            s"interpretData called with data type ${data.t} on an ADC channel. Qubit Sequencer mixup.")
        val (is, qs) = data.get[(Array[Int], Array[Int])]
        adc.interpretPhases(is, qs)

      case preamp: PreampChannel =>
        require(data.t == Type("*w"),
            s"interpretData called with data type ${data.t} on a DAC channel. Qubit Sequencer mixup.")
        preamp.interpretSwitches(data.get[Array[Long]])
    }
  }

  def getChannel(): TimingChannel = {
    channel
  }
}
