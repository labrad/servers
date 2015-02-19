package org.labrad.qubits.config

import org.labrad.data._

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
  override def packets: Seq[(String, Data)] = {
    require(startDelay > -1, s"ADC Start Delay not set for channel '$name'")
    Seq(
      "ADC Run Mode" -> Str("average"),
      "Start Delay" -> UInt(startDelay),
      "ADC Filter Func" -> Cluster(Str("balhQLIYFGDSVF"), UInt(42L), UInt(42L))
    )
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
