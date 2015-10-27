package org.labrad.qubits.channels

import org.labrad.qubits.Experiment
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.resources.DacBoard
import scala.collection.mutable

abstract class SramChannelBase[T](val name: String, val dacBoard: DacBoard) extends SramChannel {

  protected var fpga: FpgaModelDac = null

  override def fpgaModel: FpgaModelDac = {
    fpga
  }


  //
  // Blocks
  //
  protected var _currentBlock: String = null
  def currentBlock: String = {
    _currentBlock
  }
  def setCurrentBlock(block: String): Unit = {
    _currentBlock = block
  }

  protected val blocks = mutable.Map.empty[String, T]

  // Start delay
  override def startDelay: Int = {
    fpgaModel.startDelay
  }

  override def setStartDelay(startDelay: Int): Unit = {
    fpgaModel.setStartDelay(startDelay)
  }
}
