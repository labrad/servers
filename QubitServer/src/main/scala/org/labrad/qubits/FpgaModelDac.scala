package org.labrad.qubits

import org.labrad.data._
import org.labrad.qubits.channels.TriggerChannel
import org.labrad.qubits.controller.JumpTableController
import org.labrad.qubits.controller.MemoryController
import org.labrad.qubits.enums.DacTriggerId
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.resources.DacBoard
import scala.collection.mutable
import scala.concurrent.{ExecutionContext, Future}

object FpgaModelDac {
  val FREQUENCY = 25.0 // MHz
  val DAC_FREQUENCY_MHz = 1000.0
  val MAX_MEM_LEN = 256 //words per derp
  val START_DELAY_UNIT_NS = 4

  // Timing Data Conversions

  def clocksToMicroseconds(cycles: Long): Double = {
    cycles / FREQUENCY
  }

  def clocksToMicroseconds(cycles: Array[Long]): Array[Double] = {
    cycles.map(clocksToMicroseconds)
  }

  def microsecondsToClocks(microseconds: Double): Long = {
    (microseconds * FREQUENCY).toLong
  }
}

/**
 * Responsible for managing the relation between a DAC's channels and its experiment, as well as producing
 * the actual packets to send to the FPGA server.
 * Control of the DAC (by memory commands or the jump table) is delegated to the controller member variable.
 */
abstract class FpgaModelDac(val dacBoard: DacBoard, expt: Experiment) extends FpgaModel {

  import FpgaModelDac._

  private val triggers = mutable.Map.empty[DacTriggerId, TriggerChannel]

  // TODO: figure this out intelligently (from the build properties?)
  private val controller = if (dacBoard.buildNumber.toInt >= 13) {
    new JumpTableController(this)
  } else {
    new MemoryController(this)
  }

  clearController()

  def name: String = dacBoard.name

  // This method is needed by the memory SRAM commands to compute their own length.
  def experiment: Experiment = {
    expt
  }

  def packets: Seq[(String, Data)] = {
    val builder = Seq.newBuilder[(String, Data)]

    builder += "Select Device" -> Str(name)
    builder += "Start Delay" -> UInt(startDelay)
    builder ++= controller.packets

    // TODO: having the dual block stuff here is a bit ugly
    if (controller.hasDualBlockSram()) {
      val memController = this.memoryController
      builder += "SRAM dual block" -> Cluster(
          Arr(sramDualBlock1Bits),
          Arr(sramDualBlock2Bits),
          UInt(memController.sramDualBlockDelay)
      )
    } else {
      builder += "SRAM" -> Arr(sramBits)
    }
    builder.result
  }

  // Controller stuff
  def memoryController: MemoryController = {
    controller match {
      case mc: MemoryController => mc
      case _ => sys.error(s"Cannot assign memory commands to jump table board $name")
    }
  }

  def jumpTableController: JumpTableController = {
    controller match {
      case jtc: JumpTableController => jtc
      case _ => sys.error(s"Cannot assign jump table commands to memory board $name")
    }
  }

  def clearController(): Unit = {
    controller.clear()
  }
  def sequenceLength_us: Double = {
    controller.sequenceLength_us
  }
  def sequenceLengthPostSRAM_us: Double = {
    controller.sequenceLengthPostSRAM_us
  }

  private var _startDelay = 0
  def setStartDelay(startDelay: Int): Unit = {
    _startDelay = startDelay
  }
  def startDelay: Int = {
    _startDelay
  }

  //
  // Wiring
  //

  def setTriggerChannel(id: DacTriggerId, ch: TriggerChannel): Unit = {
    triggers.put(id, ch)
  }

  def samplesToMicroseconds(s: Long): Double = {
    s / DAC_FREQUENCY_MHz
  }


  //
  // SRAM
  //

  def deconvolveSram(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit]

  /**
   * Get the bits for the full SRAM sequence for this board.
   * We loop over all called blocks, padding the bits from each block
   * and then concatenating them together.
   *
   * pomalley 4/22/2014 -- Added check for hasSramChannel(), and in the
   * case where it is false, just do zeroes of the whole memory length.
   * See comment on hasSramChannel.
   * @return
   */
  def sramBits: Array[Long] = {
    val sram = if (hasSramChannel()) {
      // concatenate bits for all SRAM blocks into one array
      blockNames.toArray.flatMap { blockName =>
        val block = sramBlockBits(blockName)
        padArrayFront(block, paddedBlockLength(blockName))
        block
      }
    } else {
      var len = dacBoard.buildProperties("SRAM_LEN").toInt
      if (expt.shortestSram < len) {
        len = expt.shortestSram
      }
      Array.fill[Long](len) { 0 }
    }
    // check that the total sram sequence is not too long
    val maxLen = this.dacBoard.buildProperties("SRAM_LEN")
    if (sram.length > maxLen) {
      sys.error(s"SRAM sequence exceeds maximum length. Length = ${sram.length}; allowed = $maxLen; for board $name")
    }
    sram
  }

  /**
   * Get bits for the first block of a dual-block SRAM call
   * @return
   */
  def sramDualBlock1Bits: Array[Long] = {
    val memoryController = this.memoryController
    require(memoryController.hasDualBlockSram, "Sequence does not have a dual-block SRAM call")
    if (!hasSramChannel()) {
      // return zeros in this case
      val len = Math.min(dacBoard.buildProperties("SRAM_LEN").toInt, expt.shortestSram)
      Array.fill[Long](len) { 0 }
    } else {
      sramBlockBits(memoryController.dualBlockName1)
    }
  }

  /**
   * Get bits for the second block of a dual-block SRAM call
   * @return
   */
  def sramDualBlock2Bits: Array[Long] = {
    val memoryController = this.memoryController
    require(memoryController.hasDualBlockSram, "Sequence does not have a dual-block SRAM call")
    if (!hasSramChannel()) {
      // return zeros in this case
      val len = Math.min(dacBoard.buildProperties("SRAM_LEN").toInt, expt.shortestSram)
      Array.fill[Long](len) { 0 }
    } else {
      sramBlockBits(memoryController.dualBlockName2, addAutoTrigger = false)
    }
  }

  /**
   * Get the SRAM bits for a particular block.
   * @param block
   * @return
   */
  private def sramBlockBits(block: String, addAutoTrigger: Boolean = true): Array[Long] = {
    val sram = sramDacBits(block)
    setTriggerBits(sram, block, addAutoTrigger)
    sram
  }

  /**
   * Get DAC sram bits for a particular block.  This is
   * implemented differently for different board configurations
   * (analog vs. microwave) so it is deferred to concrete subclasses.
   * @param block
   * @return
   */
  protected def sramDacBits(block: String): Array[Long]

  /**
   * pomalley 4/22/14
   * This fpga may not have an SRAM channel if we are only using this board for FastBias control.
   * In this case, since the SRAM will be only zeroes, we won't send a sequence
   * as long as all the blocks in the Experiment object, since that may be
   * longer than the SRAM of the boards. We will only send one as long as the memory
   * of the boards.
   * @return Whether or not we have an SRAM channel (IQ or analog) for this board.
   */
  def hasSramChannel(): Boolean

  /**
   * Set trigger bits in an array of DAC bits.
   * @param s
   * @param block
   */
  private def setTriggerBits(s: Array[Long], block: String, addAutoTrigger: Boolean): Unit = {
    val autoTriggerId = expt.autoTriggerId
    var foundAutoTrigger = false

    for (ch <- triggers.values) {
      val trigs = ch.sramData(block)
      if (addAutoTrigger && (expt.autoTriggerId == ch.triggerId)) {
        foundAutoTrigger = true
        for (i <- 4 until 4 + expt.autoTriggerLen) {
          if (i < trigs.length - 1) trigs(i) = true
        }
      }
      val bit = 1L << ch.shift
      for (i <- s.indices) {
        s(i) |= (if (trigs(i)) bit else 0)
      }
    }

    // set autotrigger bits even if there is no defined trigger channel
    // TODO define dummy trigger channels, just like we do with Microwave and analog channels
    if (!foundAutoTrigger && autoTriggerId != null) {
      val bit = 1L << autoTriggerId.getShift()
      for (i <- 4 until 4 + expt.autoTriggerLen) {
        if (i < s.length - 1) s(i) |= bit
      }
    }
  }

  /**
   * Pad an array to the given length by repeating the first value the specified number of times
   * @param data
   * @param len
   * @return
   */
  protected def padArrayFront(data: Array[Long], len: Int): Array[Long] = {
    if (len <= data.length) return data
    val padding = len - data.length
    val pad = Array.fill[Long](padding) { data.head } // repeat first value
    pad ++ data
  }

  /**
   * Pad an array to the given length by repeating the first value the specified number of times
   * @param data
   * @param len
   * @return
   */
  protected def padArrayBack(data: Array[Long], len: Int): Array[Long] = {
    if (len <= data.length) return data
    val padding = len - data.length
    val pad = Array.fill[Long](padding) { data.last } // repeat last value
    data ++ pad
  }



  //
  // SRAM block management
  //

  private val blocks = mutable.Buffer.empty[String]
  private val blockLengths = mutable.Map.empty[String, Int]

  def startSramBlock(name: String, length: Long): Unit = {
    if (blocks.contains(name)) {
      require(blockLengths(name) == length,
          s"Conflicting block lengths for block $name for FPGA ${this.name} (DAC board ${dacBoard.name})")
    } else {
      blocks += name
      blockLengths(name) = length.toInt
    }
  }

  def blockNames: Seq[String] = {
    blocks.toVector
  }

  def blockLength(name: String): Int = {
    blockLengths.getOrElse(name, sys.error(s"SRAM block $name is undefined for board ${this.name}"))
  }

  /**
   * Get the proper length for an SRAM block after padding.
   * The length should be a multiple of 4 and greater or equal to 20.
   * @param name
   * @return
   */
  def paddedBlockLength(name: String): Int = {
    val len = blockLength(name)
    if (len % 4 == 0 && len >= 20) {
      len
    } else {
      val paddedLen = Math.max(len + ((4 - len % 4) % 4), 20)
      paddedLen
    }
  }

  def blockStartAddress(name: String): Int = {
    var start = 0
    for (block <- blocks) {
      if (block == name) {
        return start
      }
      start += paddedBlockLength(block)
    }
    sys.error(s"Block $name not found")
  }

  def blockEndAddress(name: String): Int = {
    var end = 0
    for (block <- blocks) {
      end += paddedBlockLength(block)
      if (block == name) {
        return end - 1 //Zero indexing ;)
      }
    }
    sys.error(s"Block $name not found")
  }

}
