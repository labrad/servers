package org.labrad.qubits.channels

import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelAnalog
import org.labrad.qubits.channeldata.AnalogData
import org.labrad.qubits.channeldata.AnalogDataFourier
import org.labrad.qubits.enums.DacAnalogId
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.util.ComplexArray

class AnalogChannel(name: String, board: DacBoard, val dacId: DacAnalogId) extends SramChannelBase[AnalogData](name, board) {

  clearConfig()

  override def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case analogDac: FpgaModelAnalog =>
        this.fpga = analogDac
        analogDac.setAnalogChannel(dacId, this)

      case _ =>
        sys.error(s"AnalogChannel '$name' requires analog board.")
    }
  }

  /**
   * Add data to the current block.
   * @param data
   */
  def addData(data: AnalogData): Unit = {
    val expected = fpga.blockLength(currentBlock)
    data.setChannel(this)
    data.checkLength(expected)
    blocks.put(currentBlock, data)
  }

  def blockData(name: String): AnalogData = {
    blocks.getOrElseUpdate(name, {
      // create a dummy data set with zeros
      val len = fpga.blockLength(name)
      val fourierLen = if (len % 2 == 0) len/2 + 1 else (len+1) / 2
      val zeros = Array.ofDim[Double](fourierLen)
      val data = new AnalogDataFourier(new ComplexArray(zeros, zeros), 0, true, false)
      data.setChannel(this)
      data
    })
  }

  def sramData(name: String): Array[Int] = {
    blocks(name).getDeconvolved()
  }


  //
  // Configuration
  //

  private var _settlingRates: Array[Double] = null
  private var _settlingAmplitudes: Array[Double] = null
  private var _reflectionRates: Array[Double] = null
  private var _reflectionAmplitudes: Array[Double] = null

  def clearConfig(): Unit = {
    _settlingRates = Array.empty[Double]
    _settlingAmplitudes = Array.empty[Double]
    _reflectionRates = Array.empty[Double]
    _reflectionAmplitudes = Array.empty[Double]
  }

  def setSettling(rates: Array[Double], amplitudes: Array[Double]): Unit = {
    require(rates.length == amplitudes.length,
        s"$name: lists of settling rates and amplitudes must be the same length")
    _settlingRates = rates
    _settlingAmplitudes = amplitudes
    // mark all blocks as needing to be deconvolved again
    for (block <- blocks.values) {
      block.invalidate()
    }
  }

  def settlingRates: Array[Double] = {
    _settlingRates.clone()
  }

  def settlingTimes: Array[Double] = {
    _settlingAmplitudes.clone()
  }

  def setReflection(rates: Array[Double], amplitudes: Array[Double]): Unit = {
    require(rates.length == amplitudes.length,
        s"$name: lists of reflection rates and amplitudes must be the same length")
    _reflectionRates = rates;
    _reflectionAmplitudes = amplitudes;
    // mark all blocks as needing to be deconvolved again
    for (block <- blocks.values) {
      block.invalidate()
    }
  }

  def reflectionRates: Array[Double] = {
    _reflectionRates.clone()
  }

  def reflectionAmplitudes: Array[Double] = {
    _reflectionAmplitudes.clone()
  }
}
