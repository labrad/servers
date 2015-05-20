package org.labrad.qubits.channels

import org.labrad.qubits.enums.DcRackFiberId

trait FiberChannel extends Channel {
  def getDcFiberId(): DcRackFiberId
  def setBiasChannel(channel: DcRackFiberId): Unit
}
