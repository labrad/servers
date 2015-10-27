package org.labrad.qubits.channels

import org.labrad.data._
import org.labrad.qubits.config.SetupPacket
import org.labrad.qubits.enums.DcRackFiberId

/**
 * Created by pomalley on 3/10/2015.
 * FastBias control via serial
 */
class FastBiasSerialChannel(name: String, dcRackCard: Int, fiberId: DcRackFiberId) extends FastBiasChannel(name, fiberId) {

  private var voltage: Double = _
  private var configured = false
  private var dac: String = _

  def configBias(dac: String, voltage: Double): Unit = {
    this.dac = dac
    this.voltage = voltage
    configured = true
  }

  def hasSetupPacket(): Boolean = {
    configured
  }

  def getSetupPacket(): SetupPacket = {
    require(hasSetupPacket(), s"Cannot get setup packet for channel '$name': it has not been configured.")
    val (dacNum, rcTimeConstant) = dac.toLowerCase match {
      case "dac0" => (0, 1)
      case "dac1slow" => (1, 1)
      case "dac1" => (1, 0)
      case _ => sys.error(s"DAC setting must be one of 'dac0', 'dac1', or 'dac1slow'. got: $dac")
    }
    val records = Seq(
      "Select Device" -> Data.NONE,
      "channel_set_voltage" -> Cluster(
        UInt(dcRackCard),
        Str(getDcFiberId.toString.toUpperCase),
        UInt(dacNum),
        UInt(rcTimeConstant),
        Value(voltage, "V")
      )
    )

    val state = s"$dcRackCard$getDcFiberId: voltage=$voltage dac=$dac"

    SetupPacket(state, records)
  }
}
