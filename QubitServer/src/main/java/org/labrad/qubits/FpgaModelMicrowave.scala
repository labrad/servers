package org.labrad.qubits

import com.google.common.collect.Lists
import java.util.List
import java.util.concurrent.Future
import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.resources.MicrowaveBoard
import org.labrad.qubits.resources.MicrowaveSource
import org.labrad.qubits.util.Futures
import scala.collection.JavaConverters._


class FpgaModelMicrowave(microwaveBoard: MicrowaveBoard, expt: Experiment) extends FpgaModelDac(microwaveBoard, expt) {

  private var iq: IqChannel = null

  def setIqChannel(iq: IqChannel): Unit = {
    this.iq = iq
  }

  def getIqChannel(): IqChannel = {
    iq
  }

  def getMicrowaveSource(): MicrowaveSource = {
    microwaveBoard.getMicrowaveSource()
  }

  def deconvolveSram(deconvolver: DeconvolutionProxy): Future[Void] = {
    val deconvolutions: List[Future[Void]] = Lists.newArrayList()
    for (blockName <- getBlockNames().asScala) {
      val block = iq.getBlockData(blockName)
      if (!block.isDeconvolved()) {
        deconvolutions.add(block.deconvolve(deconvolver))
      }
    }
    Futures.waitForAll(deconvolutions)
  }

  /**
   * Get sram bits for a particular block
   * @param block
   * @return
   */
  override protected def getSramDacBits(block: String): Array[Long] = {
    val sram = Array.fill[Long](getBlockLength(block)) { 0 }
    if (iq != null) {
      val A = iq.getSramDataA(block)
      val B = iq.getSramDataB(block)
      for (i <- A.indices) {
        sram(i) |= (A(i) & 0x3FFF).toLong + ((B(i) & 0x3FFF).toLong << 14)
      }
    }
    sram
  }

  /**
   * See comment on parent's abstract method.
   */
  override def hasSramChannel(): Boolean = {
    iq != null
  }

}
