package org.labrad.qubits.resources

import scala.collection.mutable

import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

object PreampBoard {
  def create(name: String): PreampBoard = {
    new PreampBoard(name)
  }
}

class PreampBoard(val name: String) extends BiasBoard {
  private val dacBoards = mutable.Map.empty[DcRackFiberId, DacBoard]
  private val dacFibers = mutable.Map.empty[DcRackFiberId, DacFiberId]

  def setDacBoard(channel: DcRackFiberId, board: DacBoard, fiber: DacFiberId): Unit = {
    dacBoards.put(channel, board)
    dacFibers.put(channel, fiber)
  }

  def getDacBoard(channel: DcRackFiberId): DacBoard = {
    dacBoards.getOrElse(channel, sys.error(s"No DAC board wired to channel $channel on board $name"))
  }

  def getFiber(channel: DcRackFiberId): DacFiberId = {
    dacFibers.getOrElse(channel, sys.error(s"No DAC board wired to channel $channel on board $name"))
  }
}
