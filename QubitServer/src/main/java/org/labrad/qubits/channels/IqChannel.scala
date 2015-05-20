package org.labrad.qubits.channels

import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelMicrowave
import org.labrad.qubits.channeldata.IqData
import org.labrad.qubits.channeldata.IqDataFourier
import org.labrad.qubits.config.MicrowaveSourceConfig
import org.labrad.qubits.config.MicrowaveSourceOffConfig
import org.labrad.qubits.config.MicrowaveSourceOnConfig
import org.labrad.qubits.resources.MicrowaveSource
import org.labrad.qubits.util.ComplexArray
import scala.collection.JavaConverters._

class IqChannel(name: String) extends SramChannelBase[IqData](name) {

  private var uwaveSrc: MicrowaveSource = null
  private var uwaveConfig: MicrowaveSourceConfig = null

  clearConfig()

  override def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case iqDac: FpgaModelMicrowave =>
        this.fpga = iqDac
        iqDac.setIqChannel(this)

      case _ =>
        sys.error(s"IqChannel '$getName' requires microwave board.")
    }
  }

  def getMicrowaveSource(): MicrowaveSource = {
    uwaveSrc
  }

  def setMicrowaveSource(src: MicrowaveSource): Unit = {
    uwaveSrc = src
  }

  /**
   * Add data to the current block
   * @param data
   */
  def addData(data: IqData): Unit = {
    val expected = fpga.getBlockLength(currentBlock)
    data.setChannel(this)
    data.checkLength(expected)
    blocks.put(currentBlock, data)
  }

  def getBlockData(name: String): IqData = {
    blocks.get(name) match {
      case null =>
        // create a dummy data set with zeros
        val expected = fpga.getBlockLength(name)
        val zeros = Array.fill[Double](expected) { 0 }
        val data = new IqDataFourier(new ComplexArray(zeros, zeros), 0, true)
        data.setChannel(this)
        blocks.put(name, data)
        data

      case data => data
    }
  }

  def getSramDataA(name: String): Array[Int] = {
    blocks.get(name).getDeconvolvedI()
  }

  def getSramDataB(name: String): Array[Int] = {
    blocks.get(name).getDeconvolvedQ()
  }

  // configuration

  def clearConfig(): Unit = {
    uwaveConfig = null
  }

  def configMicrowavesOn(freq: Double, power: Double): Unit = {
    uwaveConfig = new MicrowaveSourceOnConfig(freq, power)
    // mark all blocks as needing to be deconvolved again
    for (block <- blocks.values().asScala) {
      block.invalidate()
    }
  }

  def configMicrowavesOff(): Unit = {
    uwaveConfig = new MicrowaveSourceOffConfig
  }

  def getMicrowaveConfig(): MicrowaveSourceConfig = {
    require(uwaveConfig != null, s"No microwave configuration for channel '$getName'")
    uwaveConfig
  }

}
