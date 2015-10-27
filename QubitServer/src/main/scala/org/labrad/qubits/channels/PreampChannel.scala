package org.labrad.qubits.channels

import org.labrad.qubits.Experiment
import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.config.PreampConfig
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.resources.PreampBoard

class PreampChannel(val name: String, preampBoard: PreampBoard, val fiberId: DcRackFiberId) extends FiberChannel with TimingChannel {

  val dacBoard = preampBoard.getDacBoard(fiberId)
  private var expt: Experiment = null
  private var fpga: FpgaModelDac = null
  private var config: PreampConfig = null
  private var switchIntervals: Array[(Long, Long)] = null

  clearConfig()

  def getPreampBoard(): PreampBoard = {
    preampBoard
  }

  def getPreampChannel(): DcRackFiberId = {
    fiberId
  }

  def setExperiment(expt: Experiment): Unit = {
    this.expt = expt
  }

  def getExperiment(): Experiment = {
    expt
  }

  def getDacBoard(): DacBoard = {
    dacBoard
  }

  def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case dac: FpgaModelDac => this.fpga = dac
      case _ => sys.error("Preamp channel's FpgaModel must be FpgaModelDac.")
    }
  }

  override def getFpgaModel(): FpgaModelDac = {
    fpga
  }

  def startTimer(): Unit = {
    fpga.getMemoryController.startTimer()
  }

  def stopTimer(): Unit = {
    fpga.getMemoryController.stopTimer()
  }

  // configuration

  def clearConfig(): Unit = {
    config = null
  }

  def setPreampConfig(offset: Long, polarity: Boolean, highPass: String, lowPass: String): Unit = {
    config = new PreampConfig(offset, polarity, highPass, lowPass)
  }

  def hasPreampConfig(): Boolean = {
    config != null
  }

  def getPreampConfig(): PreampConfig = {
    config
  }

  /**
   * Set intervals of time that are to be interpreted as switches.
   * These are converted to FPGA memory cycles before being stored internally.
   * A single timing result will be interpreted as a switch if it lies within
   * any one of these intervals.
   * @param intervals
   */
  def setSwitchIntervals(intervals: Array[(Double, Double)]): Unit = {
    switchIntervals = intervals.map { case (a_us, b_us) =>
      val a = FpgaModelDac.microsecondsToClocks(a_us)
      val b = FpgaModelDac.microsecondsToClocks(b_us)
      (a min b, a max b)
    }
  }

  /**
   * Convert an array of cycle times to boolean switches for this channel.
   * @param cycles
   * @return
   */
  def interpretSwitches(cycles: Array[Long]): Array[Boolean] = {
    cycles map { cycle =>
      switchIntervals.exists { case (start, end) =>
        start < cycle && cycle < end
      }
    }
  }

  override def demodChannel: Int = {
    // this is a bit of a kludge, only applies to ADCs.
    -1
  }

  def getDcFiberId(): DcRackFiberId = {
    this.getPreampChannel()
  }
}
