package org.labrad.qubits

import com.google.common.collect.Lists
import com.google.common.collect.Maps
import java.util.List
import java.util.Map
import java.util.concurrent.Future
import org.labrad.qubits.channels.AnalogChannel
import org.labrad.qubits.enums.DacAnalogId
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.resources.AnalogBoard
import org.labrad.qubits.util.Futures
import scala.collection.JavaConverters._

class FpgaModelAnalog(analogBoard: AnalogBoard, expt: Experiment) extends FpgaModelDac(analogBoard, expt) {

  private val dacs: Map[DacAnalogId, AnalogChannel] = Maps.newEnumMap(classOf[DacAnalogId])

  def getAnalogBoard(): AnalogBoard = {
    analogBoard
  }

  def setAnalogChannel(id: DacAnalogId, ch: AnalogChannel): Unit = {
    dacs.put(id, ch)
  }

  def getDacChannel(id: DacAnalogId): AnalogChannel = {
    dacs.get(id)
  }

  def deconvolveSram(deconvolver: DeconvolutionProxy): Future[Void] = {
    val deconvolutions: List[Future[Void]] = Lists.newArrayList()
    for (ch <- dacs.values().asScala) {
      for (blockName <- getBlockNames().asScala) {
        val block = ch.getBlockData(blockName)
        if (!block.isDeconvolved()) {
          deconvolutions.add(block.deconvolve(deconvolver))
        }
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
    for (id <- dacs.keySet().asScala) {
      val vals = dacs.get(id).getSramData(block)
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
    !dacs.isEmpty()
  }

}
