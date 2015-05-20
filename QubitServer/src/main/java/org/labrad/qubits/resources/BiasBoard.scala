package org.labrad.qubits.resources

import org.labrad.qubits.enums.DacFiberId
import org.labrad.qubits.enums.DcRackFiberId

trait BiasBoard extends Resource {
  def setDacBoard(channel: DcRackFiberId, board: DacBoard, fiber: DacFiberId)
}
