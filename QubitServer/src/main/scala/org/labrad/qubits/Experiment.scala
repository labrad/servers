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
  for (ch <- channels[FpgaChannel]) {
    val board = ch.dacBoard
    val fpga = boards.getOrElseUpdate(board, {
      board match {
        case board: AnalogBoard => new FpgaModelAnalog(board, this)
        case board: MicrowaveBoard => new FpgaModelMicrowave(board, this)
        case board: AdcBoard => new FpgaModelAdc(board, this)
        case _ => sys.error(s"Unknown DAC board type for board ${board.name}")
      }
    })
    // connect this channel to the correct fpga model
    ch.setFpgaModel(fpga)
  }

  for (ch <- channels[FastBiasSerialChannel]) {
    // TODO: how to represent DC rack hardware in the experiment?
  }

  val fpgas = boards.values.toSet

  // sets of FPGA boards of various types
  val microwaveFpgas = fpgas.collect { case fpga: FpgaModelMicrowave => fpga }
  val dacFpgas = fpgas.collect { case dac: FpgaModelDac => dac }
  val adcFpgas = fpgas.collect { case adc: FpgaModelAdc => adc }

  // build sets of FPGA boards that have or don't have a timing channel
  val timerFpgas = channels[PreampChannel].map(_.fpgaModel).toSet
  val nonTimerFpgas = dacFpgas -- timerFpgas

  private val _setupPackets = mutable.Buffer.empty[Data]
  private val _setupState = mutable.Buffer.empty[String]
  private var _timingOrder: Seq[TimingOrderItem] = null
  private var _autoTriggerId: DacTriggerId = null
  private var _autoTriggerLen = 0

  private var _loopDelay: Double = 0
  private var _loopDelayConfigured = false

  //
  // Devices
  //

  def device(name: String): Device = {
    devicesByName.get(name).getOrElse {
      sys.error(s"Device '$name' not found.")
    }
  }

  def channels[T <: Channel : ClassTag]: Seq[T] = {
    devices.flatMap(_.getChannels[T])
  }


  //
  // FPGAs
  //

  /**
   * Clear the memory or jump table commands for these FPGAs.
   */
  def clearControllers(): Unit = {
    for (fpga <- dacFpgas) {
      fpga.clearController()
    }
  }

  def fpgaNames: Seq[String] = {
    fpgas.map(_.name).toSeq
  }

  /**
   * Clear all configuration that has been set for this experiment
   */
  def clearConfig(): Unit = {
    // reset setup packets
    clearSetupState()

    // clear timing order
    _timingOrder = null

    // clear autotrigger
    _autoTriggerId = null

    // clear configuration on all channels
    for {
      dev <- devices
      ch <- dev.getChannels()
    } {
      ch.clearConfig()
    }

    // de-configure loopDelay
    _loopDelayConfigured = false
  }


  private def clearSetupState(): Unit = {
    _setupState.clear()
    _setupPackets.clear()
  }

  def setSetupState(state: Seq[String], packets: Seq[Data]): Unit = {
    clearSetupState()
    _setupState ++= state
    _setupPackets ++= packets
  }

  def setupState: Seq[String] = {
    _setupState.toVector
  }

  def setupPackets: Seq[Data] = {
    _setupPackets.toVector
  }

  def setAutoTrigger(id: DacTriggerId, length: Int): Unit = {
    _autoTriggerId = id
    _autoTriggerLen = length
  }

  def autoTriggerId: DacTriggerId = {
    _autoTriggerId
  }

  def autoTriggerLen: Int = {
    _autoTriggerLen
  }

  def setTimingOrder(to: Seq[TimingOrderItem]): Unit = {
    _timingOrder = to
  }

  def configLoopDelay(loopDelay: Double): Unit = {
    _loopDelay = loopDelay
    _loopDelayConfigured = true
  }

  def isLoopDelayConfigured(): Boolean = {
    _loopDelayConfigured
  }
  def loopDelay: Double = {
    _loopDelay
  }

  /**
   * Get the order of boards from which to return timing data
   * @return
   */
  def timingOrder: Seq[String] = {
    timingChannels.map(_.toString)
  }

  def timingChannels: Seq[TimingOrderItem] = {
    // if we have an existing timing order, use it
    if (_timingOrder != null) {
      _timingOrder
    // if not, use everything--all DACs, all ADCs/active ADC channels
    } else {
      channels[TimingChannel].map {
        case t: AdcChannel => new TimingOrderItem(t, t.demodChannel)
        case t => new TimingOrderItem(t)
      }
    }
  }

  def adcTimingOrderIndices(): Seq[Int] = {
    timingChannels.zipWithIndex.collect {
      case (toi, i) if toi.isAdc => i
    }
  }

  def dacTimingOrderIndices(): Seq[Int] = {
    timingChannels.zipWithIndex.collect {
      case (toi, i) if !toi.isAdc => i
    }
  }

  //
  // Jump Table
  //

  def addJumpTableEntry(commandName: String, commandData: Data): Unit = {
    for (fpga <- dacFpgas) {
      fpga.jumpTableController.addJumpTableEntry(commandName, commandData)
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
    for (fpga <- dacFpgas) {
      allCmds.get(fpga) match {
        case Some(cmds) =>
          fpga.memoryController.addMemoryCommands(cmds)
          fpga.memoryController.addMemoryNoops(maxCmds - cmds.size)

        case None =>
          fpga.memoryController.addMemoryNoops(maxCmds)
      }
      if (delay > 0) {
        fpga.memoryController.addMemoryDelay(delay)
      }
    }
  }

  /**
   * Add a delay command to exactly one board
   *
   */
  def addSingleMemoryDelay(fpga: FpgaModelDac, delay_us: Double): Unit = {
    fpga.memoryController.addMemoryDelay(delay_us)
  }

  /**
   * Add a delay in the memory sequence of all boards.
   * Only applies to DACs.
   */
  def addMemoryDelay(microseconds: Double): Unit = {
    for (fpga <- dacFpgas) {
      fpga.memoryController.addMemoryDelay(microseconds)
    }
  }

  def addMemSyncDelay(): Unit = {
    //Find maximum sequence length on all fpgas
    var maxT_us = 0.0
    for (fpga <- fpgas) {
      try {
        val t_us = fpga.sequenceLengthPostSRAM_us
        maxT_us = Math.max(maxT_us, t_us)
      } catch {
        case ex: java.lang.IllegalArgumentException =>
      }
    }

    for (fpga <- dacFpgas) {
      var t = 0.0
      try {
        t = fpga.sequenceLength_us
      } catch {
        case ex: java.lang.IllegalArgumentException =>
      }
      if (t < maxT_us) {
        fpga.memoryController.addMemoryDelay(maxT_us - t)
      } else {
        fpga.memoryController.addMemoryNoop()
      }
    }
  }

  /**
   * Call SRAM. Only applies to DACs.
   */
  def callSramBlock(block: String): Unit = {
    for (fpga <- dacFpgas) {
      fpga.memoryController.callSramBlock(block)
    }
  }

  def callSramDualBlock(block1: String, block2: String): Unit = {
    for (fpga <- dacFpgas) {
      fpga.memoryController.callSramDualBlock(block1, block2)
    }
  }

  def setSramDualBlockDelay(delay_ns: Double): Unit = {
    for (fpga <- dacFpgas) {
      fpga.memoryController.setSramDualBlockDelay(delay_ns)
    }
  }

  /**
   * Get the length of the shortest SRAM block across all fpgas.
   * @return
   */
  def shortestSram: Int = {
    val lens = for {
      fpga <- dacFpgas
      block <- fpga.blockNames
    } yield fpga.blockLength(block)

    if (lens.isEmpty) 0 else lens.min
  }

  /**
   * Start timer on a set of boards.
   * This only applies to DAC fpgas.
   */
  def startTimer(channels: Seq[PreampChannel]): Unit = {
    val boards = channels.map(_.fpgaModel).toSet

    // start requested timers
    val timerStarts = boards
    val timerNoops = timerFpgas -- boards

    // start non timer boards that have never been started
    val (nonTimerNoops, nonTimerStarts) = nonTimerFpgas.partition(_.memoryController.isTimerStarted)

    // start the timer on requested boards
    for (fpga <- timerStarts ++ nonTimerStarts) {
      fpga.memoryController.startTimer()
    }
    // insert a no-op on all other boards
    for (fpga <- timerNoops ++ nonTimerNoops) {
      fpga.memoryController.addMemoryNoop()
    }
  }

  /**
   * Stop timer on a set of boards.
   */
  def stopTimer(channels: Seq[PreampChannel]): Unit = {
    val boards = channels.map(_.fpgaModel).toSet

    // stop requested timers
    val timerStops = boards
    val timerNoops = timerFpgas -- boards

    // stop non-timer boards if they are currently running
    val (nonTimerStops, nonTimerNoops) = nonTimerFpgas.partition(_.memoryController.isTimerRunning)

    // stop the timer on requested boards and non-timer boards
    for (fpga <- timerStops ++ nonTimerStops) {
      fpga.memoryController.stopTimer()
    }
    // insert a no-op on all other boards
    for (fpga <- timerNoops ++ nonTimerNoops) {
      fpga.memoryController.addMemoryNoop()
    }
  }

}

// stupid handler class to implement a timing order item
class TimingOrderItem(val channel: TimingChannel, subChannel: Int = -1) {

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
}
