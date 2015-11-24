package org.labrad.qubits

import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.resources.MicrowaveBoard
import org.labrad.qubits.resources.MicrowaveSource
import scala.concurrent.{ExecutionContext, Future}

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

  def deconvolveSram(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    val deconvolutions = for {
      blockName <- getBlockNames()
      block = iq.getBlockData(blockName)
      if !block.isDeconvolved
    } yield block.deconvolve(deconvolver)

    Future.sequence(deconvolutions).map { _ => () } // discard results
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
