package org.labrad.qubits.channels

import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.channeldata.TriggerData
import org.labrad.qubits.channeldata.TriggerDataTime
import org.labrad.qubits.enums.DacTriggerId
import org.labrad.qubits.resources.DacBoard

class TriggerChannel(name: String, board: DacBoard, triggerId: DacTriggerId) extends SramChannelBase[TriggerData](name, board) {

  override def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case dac: FpgaModelDac =>
        this.fpga = dac
        dac.setTriggerChannel(triggerId, this)

      case _ =>
        sys.error(s"TriggerChannel '$name' requires FpgaModelDac.")
    }
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
    val trigger = blocks.getOrElseUpdate(name, {
      // create a dummy data block
      val length = fpga.getBlockLength(name)
      val zeros = Array.ofDim[Boolean](length)
      val d = new TriggerDataTime(zeros)
      d.setChannel(this)
      d
    })
    trigger.get()
  }

  // configuration

  def clearConfig(): Unit = {
    // nothing to do here
  }
}
