package org.labrad.qubits.config

import org.labrad.data._

case class SetupPacket(state: String, records: Seq[(String, Data)]) {
  def recordData: Data = {
    val recordClusters = records.map {
      case (setting, Data.NONE) => Cluster(Str(setting)) // Can't include NONEs inside larger structures. TODO: fix this
      case (setting, data) => Cluster(Str(setting), data)
    }
    Cluster(recordClusters: _*)
  }
}
