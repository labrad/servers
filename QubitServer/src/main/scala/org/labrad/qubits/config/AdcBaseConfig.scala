package org.labrad.qubits.config

import org.labrad.data.Data

abstract class AdcBaseConfig(channelName: String, builProperties: Map[String, Long]) {

  /**
   * number of clock cycles to delay
   */
  protected var startDelay: Int = -1

  def setStartDelay(startDelay: Int): Unit = {
    this.startDelay = startDelay
  }

  /**
   * Adds packets to a labrad request to the fpga server.
   * These packets configure the ADC. The ADC must already have been
   * selected in this request.
   * @param runRequest The request to which we add the packets.
   * @author pomalley
   */
  def packets: Seq[(String, Data)]

  /**
   * Converts Is and Qs to T/F based on the previously given critical phase.
   * switched = (atan2(q, i) < criticalPhase)
   * @param is
   * @param is2
   * @param channel Demodulation channel (-1 for average mode)
   * @return
   */
  def interpretPhases(Is: Array[Int], Qs: Array[Int], channel: Int): Array[Boolean]

  def getStartDelay(): Int = {
    startDelay
  }

}
