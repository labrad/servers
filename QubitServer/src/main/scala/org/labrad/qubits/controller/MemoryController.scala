package org.labrad.qubits.controller

import org.labrad.data._
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.mem._
import scala.collection.mutable

/**
 * The MemoryController
 */
class MemoryController(fpga: FpgaModelDac) extends FpgaController(fpga) {

  private val memory = mutable.Buffer.empty[MemoryCommand]
  private var timerStartCount = 0
  private var timerStopCount = 0
  private var sramCalled = false
  private var sramCalledDualBlock = false
  private var sramDualBlockCmd: CallSramDualBlockCommand = null
  private var sramDualBlockDelay: Double = -1

  def packets: Seq[(String, Data)] = {
    Seq(
      "Memory" -> Arr(getMemory())
    )
  }

  def clear(): Unit = {
    memory.clear()
    timerStartCount = 0
    timerStopCount = 0
    sramCalled = false
    sramCalledDualBlock = false
    sramDualBlockCmd = null
  }

  def addMemoryCommand(cmd: MemoryCommand): Unit = {
    memory += cmd
  }

  def addMemoryCommands(cmds: Seq[MemoryCommand]): Unit = {
    memory ++= cmds
  }

  def addMemoryNoop(): Unit = {
    addMemoryCommand(NoopCommand)
  }

  def addMemoryNoops(n: Int): Unit = {
    for (i <- 0 until n) {
      addMemoryCommand(NoopCommand)
    }
  }

  def addMemoryDelay(microseconds: Double): Unit = {
    val cycles = FpgaModelDac.microsecondsToClocks(microseconds).toInt
    val memSize = this.memory.size
    if (memSize > 0) {
      val lastCmd = this.memory(memSize - 1)
      lastCmd match {
        case delayCmd: DelayCommand =>
          delayCmd.setDelay(cycles + delayCmd.getDelay)

        case _ =>
          addMemoryCommand(new DelayCommand(cycles))
      }
    } else {
      addMemoryCommand(new DelayCommand(cycles))
    }
  }



  override def getSequenceLength_us(): Double = {
    var t_us = this.fpga.getStartDelay() * FpgaModelDac.START_DELAY_UNIT_NS / 1000.0
    for (memCmd <- this.memory) {
      t_us += memCmd.getTime_us(fpga)
    }
    t_us
  }
  override def getSequenceLengthPostSRAM_us(): Double = {
    var t_us = this.fpga.getStartDelay() * FpgaModelDac.START_DELAY_UNIT_NS / 1000.0
    var SRAMStarted = false
    for (memCmd <- this.memory) {
      if (memCmd.isInstanceOf[CallSramDualBlockCommand] || memCmd.isInstanceOf[CallSramCommand]) {
        SRAMStarted = true
      }
      if (SRAMStarted) {
        t_us += memCmd.getTime_us(fpga)
      }
    }
    t_us
  }
  // timer logic

  /**
   * Check whether the timer has been started at least once
   * @return
   */
  def isTimerStarted(): Boolean = {
    timerStartCount > 0
  }

  /**
   * Check whether the timer is currently running (has been started but not yet stopped)
   * @return
   */
  def isTimerRunning(): Boolean = {
    timerStartCount == timerStopCount + 1
  }

  /**
   * Check whether the timer is currently stopped
   * @return
   */
  def isTimerStopped(): Boolean = {
    timerStartCount == timerStopCount
  }

  /**
   * Check that the timer status of this board is ok, namely that the timer
   * has been started at least once and stopped as many times as it has been
   * started.  This ensures that all boards will be run properly.
   */
  def checkTimerStatus(): Unit = {
    require(isTimerStarted(), s"${fpga.name}: timer not started")
    require(isTimerStopped(), s"${fpga.name}: timer not stopped")
  }

  /**
   * Issue a start timer command.  Will only succeed if the timer is currently stopped.
   */
  def startTimer(): Unit = {
    require(isTimerStopped(), s"${fpga.name}: timer already started")
    addMemoryCommand(StartTimerCommand)
    timerStartCount += 1
  }

  /**
   * Issue a stop timer command.  Will only succeed if the timer is currently running.
   */
  def stopTimer(): Unit = {
    require(isTimerRunning(), s"${fpga.name}: timer not started")
    addMemoryCommand(StopTimerCommand)
    timerStopCount += 1
  }

  // SRAM calls

  //
  // SRAM
  //

  def callSramBlock(blockName: String): Unit = {
    require(!sramCalledDualBlock, "Cannot call SRAM and dual-block in the same sequence.")
    addMemoryCommand(new CallSramCommand(blockName))
    sramCalled = true
  }

  def callSramDualBlock(block1: String, block2: String): Unit = {
    require(!sramCalled, "Cannot call SRAM and dual-block in the same sequence.")
    require(!sramCalledDualBlock, "Only one dual-block SRAM call allowed per sequence.")
    val cmd = new CallSramDualBlockCommand(block1, block2, sramDualBlockDelay)
    addMemoryCommand(cmd)
    sramDualBlockCmd = cmd
    sramCalledDualBlock = true
  }

  def setSramDualBlockDelay(delay_ns: Double): Unit = {
    sramDualBlockDelay = delay_ns
    if (sramCalledDualBlock) {
      // need to update the already-created dual-block command
      sramDualBlockCmd.setDelay(delay_ns)
    }
  }

  override def hasDualBlockSram(): Boolean = {
    sramCalledDualBlock
  }

  /**
   * Get the delay between blocks in a dual-block SRAM call
   * @return
   */
  def getSramDualBlockDelay(): Long = {
    require(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call")
    sramDualBlockCmd.getDelay().toLong
  }



  //
  // bit sequences
  //

  /**
   * Get the bits of the memory sequence for this board
   */
  def getMemory(): Array[Long] = {
    // add initial noop and final mem commands
    val mem = NoopCommand +: memory.toArray :+ EndSequenceCommand

    // resolve addresses of all SRAM blocks
    for (c <- mem) {
      c match {
        case cmd: CallSramCommand =>
          val block = cmd.getBlockName()
          if (fpga.getBlockNames().contains(block)) {
            cmd.setStartAddress(fpga.getBlockStartAddress(block))
            cmd.setEndAddress(fpga.getBlockEndAddress(block))
          } else {
            // if this block wasn't defined for us, then it will be filled with zeros
            cmd.setStartAddress(0)
            cmd.setEndAddress(fpga.getExperiment().getShortestSram())
          }

        case _ => // do nothing
      }
    }

    // get bits for all memory commands
    val bits = mem.flatMap(_.getBits)

    // check that the total memory sequence is not too long
    if (bits.length > fpga.getDacBoard.buildProperties("SRAM_WRITE_PKT_LEN")) {
      sys.error("Memory sequence exceeds maximum length")
    }
    bits
  }

  def getDualBlockName1(): String = {
    require(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call")
    sramDualBlockCmd.getBlockName1()
  }

  def getDualBlockName2(): String = {
    require(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call")
    sramDualBlockCmd.getBlockName2()
  }
}
