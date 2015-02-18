package org.labrad.qubits.channels

import org.labrad.data.Data
import org.labrad.qubits.config.SetupPacket

/**
 * Created by pomalley on 3/10/2015.
 * FastBias control via serial
 */
class FastBiasSerialChannel(name: String) extends FastBiasChannel(name) {

  private var dcRackCard: Int = _
  private var voltage: Double = _
  private var configured = false
  private var dac: String = _

  def setDCRackCard(dcRackCard: Int): Unit = {
    this.dcRackCard = dcRackCard
  }

  def setBias(voltage: Double): Unit = {
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
    val data = Data.ofType("(s)(s(wswwv[V]))")
    data.get(0).setString("Select Device", 0)
    data.get(1).setString("channel_set_voltage", 0)
            .setWord(dcRackCard, 1, 0)
            .setString(getDcFiberId().toString().toUpperCase(), 1, 1)
            .setWord(dacNum, 1, 2)
            .setWord(rcTimeConstant, 1, 3)
            .setValue(voltage, 1, 4)

    val state = "%d%s: voltage=%f dac=%s".format(
            dcRackCard, getDcFiberId(), voltage, dac)
    new SetupPacket(state, data)
  }

  def setDac(dac: String): Unit = {
    this.dac = dac
  }
}
