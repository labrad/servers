package org.labrad.qubits.resources

import java.util.Map

import org.labrad.data.Data
import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

import com.google.common.collect.Maps

object FastBias {
  def create(name: String, properties: Seq[Data]): FastBias = {
    val board = new FastBias(name)
    board.setProperties(properties)
    board
  }
}

class FastBias(name: String) extends BiasBoard {
  private val dacBoards: Map[DcRackFiberId, DacBoard] = Maps.newHashMap()
  private val dacFibers: Map[DcRackFiberId, DacFiberId] = Maps.newHashMap()
  private val gains: Map[DcRackFiberId, Double] = Maps.newHashMap()

  def getName: String = {
    name
  }

  def setDacBoard(channel: DcRackFiberId, board: DacBoard, fiber: DacFiberId) {
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

  def getGain(channel: DcRackFiberId): Double = {
    if (gains.containsKey(channel)) {
      gains.get(channel)
    } else {
      1.0
    }
  }

  private def setProperties(properties: Seq[Data]): Unit = {
    for (elem <- properties) {
      val name = elem.get(0).getString()
      if (name == "gain") {
        val channels = DcRackFiberId.values()
        val values = elem.get(1).getValueArray()
        for ((ch, gain) <- channels zip values) {
          gains.put(ch, gain)
        }
      }
    }
  }
}
