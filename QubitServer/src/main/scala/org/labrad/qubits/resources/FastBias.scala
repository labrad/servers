package org.labrad.qubits.resources

import scala.collection.mutable

import org.labrad.data.Data
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

object FastBias {
  def create(name: String, properties: Seq[Data]): FastBias = {
    val board = new FastBias(name)
    board.setProperties(properties)
    board
  }
}

class FastBias(val name: String) extends BiasBoard {
  private val dacBoards = mutable.Map.empty[DcRackFiberId, DacBoard]
  private val dacFibers = mutable.Map.empty[DcRackFiberId, DacFiberId]
  private val gains = mutable.Map.empty[DcRackFiberId, Double]

  def setDacBoard(channel: DcRackFiberId, board: DacBoard, fiber: DacFiberId) {
    dacBoards.put(channel, board)
    dacFibers.put(channel, fiber)
  }

  def getDacBoard(channel: DcRackFiberId): DacBoard = {
    dacBoards.getOrElse(channel, sys.error(s"No DAC board wired to channel $channel on board $name"))
  }

  def getFiber(channel: DcRackFiberId): DacFiberId = {
    dacFibers.getOrElse(channel, sys.error(s"No DAC board wired to channel $channel on board $name"))
  }

  def getGain(channel: DcRackFiberId): Double = {
    gains.getOrElse(channel, 1.0)
  }

  private def setProperties(properties: Seq[Data]): Unit = {
    for (elem <- properties) {
      val name = elem(0).getString
      if (name == "gain") {
        val channels = DcRackFiberId.values()
        val values = elem(1).get[Array[Double]]
        for ((ch, gain) <- channels zip values) {
          gains(ch) = gain
        }
      }
    }
  }
}
