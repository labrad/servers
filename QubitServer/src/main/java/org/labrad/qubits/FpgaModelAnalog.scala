package org.labrad.qubits

import org.labrad.qubits.channels.AnalogChannel
import org.labrad.qubits.enums.DacAnalogId
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.resources.AnalogBoard
import scala.collection.mutable
import scala.concurrent.{ExecutionContext, Future}

class FpgaModelAnalog(analogBoard: AnalogBoard, expt: Experiment) extends FpgaModelDac(analogBoard, expt) {

  private val dacs = mutable.Map.empty[DacAnalogId, AnalogChannel]

  def getAnalogBoard(): AnalogBoard = {
    analogBoard
  }

  def setAnalogChannel(id: DacAnalogId, ch: AnalogChannel): Unit = {
    dacs(id) = ch
  }

  def getDacChannel(id: DacAnalogId): AnalogChannel = {
    dacs(id)
  }

  def deconvolveSram(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    val deconvolutions = for {
      ch <- dacs.values.toVector
      blockName <- getBlockNames
      block = ch.getBlockData(blockName)
      if !block.isDeconvolved()
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
    for (id <- dacs.keys) {
      val vals = dacs(id).getSramData(block)
      for (i <- vals.indices) {
        sram(i) |= ((vals(i) & 0x3FFF).toLong << id.getShift())
      }
    }
    sram
  }

  /**
   * See comments on parent's abstract method.
   */
  override def hasSramChannel(): Boolean = {
    dacs.nonEmpty
  }

}
