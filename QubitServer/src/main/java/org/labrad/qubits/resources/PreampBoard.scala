package org.labrad.qubits.resources

import java.util.Map

import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

import com.google.common.collect.Maps

object PreampBoard {
  def create(name: String): PreampBoard = {
    new PreampBoard(name)
  }
}

class PreampBoard(name: String) extends BiasBoard {
  private val dacBoards: Map[DcRackFiberId, DacBoard] = Maps.newHashMap()
  private val dacFibers: Map[DcRackFiberId, DacFiberId] = Maps.newHashMap()

  def getName(): String = {
    name
  }

  def setDacBoard(channel: DcRackFiberId, board: DacBoard, fiber: DacFiberId): Unit = {
    dacBoards.put(channel, board)
    dacFibers.put(channel, fiber)
  }

  def getDacBoard(channel: DcRackFiberId): DacBoard = {
    require(dacBoards.containsKey(channel),
        s"No DAC board wired to channel '$channel' on board '$name'")
    dacBoards.get(channel)
  }

  def getFiber(channel: DcRackFiberId): DacFiberId = {
    require(dacBoards.containsKey(channel),
        s"No DAC board wired to channel '$channel' on board '$name'")
    dacFibers.get(channel)
  }
}
