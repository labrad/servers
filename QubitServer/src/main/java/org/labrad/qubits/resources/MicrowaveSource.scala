package org.labrad.qubits.resources

import java.util.Set

import com.google.common.collect.Sets

object MicrowaveSource {
  def create(name: String): MicrowaveSource = {
    new MicrowaveSource(name)
  }
}

class MicrowaveSource(val name: String) extends Resource {
  private val boards: Set[MicrowaveBoard] = Sets.newHashSet()

  def addMicrowaveBoard(board: MicrowaveBoard): Unit = {
    boards.add(board)
  }

  def getMicrowaveBoards(): Set[MicrowaveBoard] = {
    boards
  }

  def getName(): String = name
}
