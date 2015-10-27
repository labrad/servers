package org.labrad.qubits.channels

import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelDac
import org.labrad.qubits.enums.DcRackFiberId
import org.labrad.qubits.resources.DacBoard

/**
 * Created by pomalley on 3/10/2015.
 * FastBias control via FPGA.
 */
class FastBiasFpgaChannel(name: String, val dacBoard: DacBoard, fiberId: DcRackFiberId) extends FastBiasChannel(name, fiberId) with FpgaChannel {

  private var fpga: FpgaModelDac = _

  def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case dac: FpgaModelDac => this.fpga = dac
      case _ => sys.error(s"FastBias $name requires an FpgaModelDac.")
    }
  }

  def getFpgaModel(): FpgaModelDac = {
    fpga
  }
}
