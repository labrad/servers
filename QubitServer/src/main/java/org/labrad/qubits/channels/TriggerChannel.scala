package org.labrad.qubits.channels

import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.channeldata.TriggerData
import org.labrad.qubits.channeldata.TriggerDataTime
import org.labrad.qubits.enums.DacTriggerId

class TriggerChannel(name: String) extends SramChannelBase[TriggerData](name) {

  private var triggerId: DacTriggerId = null

  override def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case dac: FpgaModelDac =>
        this.fpga = dac
        dac.setTriggerChannel(triggerId, this)

      case _ =>
        sys.error(s"TriggerChannel '$getName' requires FpgaModelDac.")
    }
  }

  def setTriggerId(id: DacTriggerId): Unit = {
    triggerId = id
  }

  def getShift(): Int = {
    triggerId.getShift()
  }

  def getTriggerId(): DacTriggerId = {
    triggerId
  }

  def addData(data: TriggerData): Unit = {
    val expected = fpga.getBlockLength(currentBlock)
    data.checkLength(expected)
    blocks.put(currentBlock, data)
  }

  def addPulse(start: Int, len: Int): Unit = {
    val data = getSramData(currentBlock)
    val newStart = Math.max(0, start)
    val end = Math.min(data.length, newStart + len)
    for (i <- start until end) {
      data(i) = true
    }
  }

  def getSramData(name: String): Array[Boolean] = {
    val d = blocks.get(name) match {
      case null =>
        // create a dummy data block
        val length = fpga.getBlockLength(name)
        val zeros = Array.ofDim[Boolean](length)
        val d = new TriggerDataTime(zeros)
        d.setChannel(this)
        blocks.put(name, d)
        d

      case d => d
    }
    d.get()
  }

  // configuration

  def clearConfig(): Unit = {
    // nothing to do here
  }
}
