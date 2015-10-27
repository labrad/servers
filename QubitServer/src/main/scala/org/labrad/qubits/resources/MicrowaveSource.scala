package org.labrad.qubits.resources

import scala.collection.mutable

object MicrowaveSource {
  def create(name: String): MicrowaveSource = {
    new MicrowaveSource(name)
  }
}

class MicrowaveSource(val name: String) extends Resource {
  private val boards = mutable.Set.empty[MicrowaveBoard]

  def addMicrowaveBoard(board: MicrowaveBoard): Unit = {
    boards += board
  }

  def microwaveBoards: Set[MicrowaveBoard] = {
    boards.toSet
  }
}
