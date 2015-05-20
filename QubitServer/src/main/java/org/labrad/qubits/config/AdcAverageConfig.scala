package org.labrad.qubits.config

import java.util.Map

import org.labrad.data.Data
import org.labrad.data.Request

class AdcAverageConfig(name: String, buildProperties: Map[String, Long]) extends AdcBaseConfig(name, buildProperties) {

  private var criticalPhase: Double = 0

  /**
   * in the Average mode, the following packets are added:
   * ADC Run Mode
   * Start Delay
   * ... and that's it.
   * @param runRequest The request to which we add the packets.
   * @author pomalley
   */
  override def addPackets(runRequest: Request): Unit = {
    require(startDelay > -1, s"ADC Start Delay not set for channel '$name'")
    runRequest.add("ADC Run Mode", Data.valueOf("average"))
    runRequest.add("Start Delay", Data.valueOf(this.startDelay.toLong))
    runRequest.add("ADC Filter Func", Data.valueOf("balhQLIYFGDSVF"), Data.valueOf(42L), Data.valueOf(42L))
  }

  def setCriticalPhase(criticalPhase: Double): Unit = {
    require(criticalPhase >= 0.0 && criticalPhase <= 2*Math.PI,
        "Critical phase must be between 0 and 2PI")
    this.criticalPhase = criticalPhase
  }

  override def interpretPhases(Is: Array[Int], Qs: Array[Int], channel: Int): Array[Boolean] = {
    require(Is.length == Qs.length, "Is and Qs must have same length!")
    if (channel != -1) {
      println("WARNING: interpretPhases for average mode ADC called with demod channel != -1")
    }
    (Is zip Qs).map { case (i, q) =>
      Math.atan2(q, i) < criticalPhase
    }
  }

}
