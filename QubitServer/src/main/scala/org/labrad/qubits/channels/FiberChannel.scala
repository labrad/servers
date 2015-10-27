package org.labrad.qubits.channels

import org.labrad.qubits.enums.DcRackFiberId

trait FiberChannel extends Channel {
  val dcRackFiberId: DcRackFiberId
}
