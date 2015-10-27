package org.labrad.qubits.channels

import org.labrad.data._
import org.labrad.qubits.Experiment
import org.labrad.qubits.FpgaModel
import org.labrad.qubits.FpgaModelAdc
import org.labrad.qubits.enums.AdcMode
import org.labrad.qubits.resources.AdcBoard

/**
 * This channel represents a connection to an ADC in demodulation mode.
 *
 * @author pomalley
 *
 */
class AdcChannel(val name: String, val dacBoard: AdcBoard) extends Channel with TimingChannel with StartDelayChannel {

  private val props = dacBoard.buildProperties
  val MAX_CHANNELS = props("DEMOD_CHANNELS").toInt
  val DEMOD_CHANNELS_PER_PACKET = props("DEMOD_CHANNELS_PER_PACKET").toInt
  val TRIG_AMP = props("TRIG_AMP").toInt
  // see fpga server documentation on the "ADC Demod Phase" setting for an explanation of the two below.
  val LOOKUP_ACCUMULATOR_BITS = props("LOOKUP_ACCUMULATOR_BITS").toInt
  val DEMOD_TIME_STEP = props("DEMOD_TIME_STEP").toInt // in ns

  private var expt: Experiment = null
  private var fpga: FpgaModelAdc = null

  // configuration variables
  private var mode: AdcMode = AdcMode.UNSET // DEMODULATE, AVERAGE, UNSET
  // passed to filter function setting
  private var filterFunction: String = null
  private var stretchLen: Int = _
  private var stretchAt: Int = _

  private var criticalPhase: Double = _ // used to interpret phases (into T/F switches)
  private var _demodChannel: Int = _ // which demod channel are we (demod mode only)

  // passed to "ADC Demod Phase" setting of FPGA server (demod mode only)
  private var dPhi: Int = _
  private var phi0: Int = _

  // passed to "ADC Trig Magnitude" setting (demod mode only)
  private var ampSin: Int = _
  private var ampCos: Int = _

  private var triggerTable: Data = null // passed to "ADC Trigger Table"
  private var mixerTable: Data = null // passed to "ADC Mixer Table"

  private var reverseCriticalPhase: Boolean = false

  private var offsetI: Int = _
  private var offsetQ: Int = _

  clearConfig()

  override def getExperiment(): Experiment = {
    expt
  }

  override def getFpgaModel(): FpgaModelAdc = {
    fpga
  }

  override def setExperiment(expt: Experiment): Unit = {
    this.expt = expt
  }

  override def setFpgaModel(fpga: FpgaModel): Unit = {
    fpga match {
      case adc: FpgaModelAdc =>
        this.fpga = adc
        adc.setChannel(this)

      case _ =>
        sys.error(s"AdcChannel '$name' requires ADC board.")
    }
  }

  // reconcile this ADC configuration with another one for the same ADC.
  def reconcile(other: AdcChannel): Boolean = {
    if (this.dacBoard != other.dacBoard)
      return false
    if (this == other)
      return true
    require(this.mode == other.mode,
        s"Conflicting modes for ADC board ${dacBoard.name}")
    require(this.startDelay == other.startDelay,
        s"Conflicting start delays for ADC board ${dacBoard.name}")
    require(this.triggerTable == other.triggerTable,
        s"Conflicting trigger tables for ADC board ${dacBoard.name}: (this: ${this.triggerTable}, other: ${other.triggerTable})")
    mode match {
      case AdcMode.DEMODULATE =>
        require(this.filterFunction == other.filterFunction,
            s"Conflicting filter functions for ADC board ${dacBoard.name}")
        require(this.stretchAt == other.stretchAt,
            s"Conflicting stretchAt parameters for ADC board ${dacBoard.name}")
        require(this.stretchLen == other.stretchLen,
            s"Conflicting stretchLen parameters for ADC board ${dacBoard.name}")
        require(this.demodChannel != other.demodChannel,
            s"Two ADC Demod channels with same channel number for ADC board ${dacBoard.name}")

      case AdcMode.AVERAGE =>
        // nothing?

      case AdcMode.UNSET =>
        sys.error(s"ADC board ${dacBoard.name} has no mode (avg/demod) set!")
    }
    true
  }

  // add global packets for this ADC board. should only be called on one channel per board!
  def globalPackets: Seq[(String, Data)] = {
    val packets = Seq.newBuilder[(String, Data)]
    mode match {
      case AdcMode.AVERAGE =>
        require(startDelay > -1, s"ADC Start Delay not set for channel '$name'")
        packets += "ADC Run Mode" -> Str("average")
        packets += "Start Delay" -> UInt(startDelay)

      case AdcMode.DEMODULATE =>
        require(startDelay > -1, s"ADC Start Delay not set for channel $name")
        packets += "ADC Run Mode" -> Str("demodulate")
        packets += "Start Delay" -> UInt(startDelay)

      case AdcMode.UNSET =>
        sys.error(s"ADC channel $name has no mode (avg/demod) set!")
    }
    if (triggerTable != null) {
      packets += "ADC Trigger Table" -> triggerTable
    }
    packets.result
  }

  // add local packets. only really applicable for demod mode
  def localPackets: Seq[(String, Data)] = {
    val packets = Seq.newBuilder[(String, Data)]
    /*
    if (this.mode == AdcMode.DEMODULATE) {
      Preconditions.checkState(ampSin > -1 && ampCos > -1, "ADC Trig Magnitude not set on demod channel %s on channel '%s'", this.demodChannel, this.name);
      runRequest.add("ADC Demod Phase", Data.valueOf((long)this.demodChannel), Data.valueOf(dPhi), Data.valueOf(phi0));
      runRequest.add("ADC Trig Magnitude", Data.valueOf((long)this.demodChannel), Data.valueOf((long)ampSin), Data.valueOf((long)ampCos));
    }
    */
    if (mixerTable != null) {
      packets += "ADC Mixer Table" -> Cluster(UInt(demodChannel), mixerTable)
    }
    packets.result
  }

  //
  // Critical phase functions
  //

  def setCriticalPhase(criticalPhase: Double): Unit = {
    require(criticalPhase >= -Math.PI && criticalPhase <= Math.PI,
        s"Critical phase must be between -PI and PI")
    this.criticalPhase = criticalPhase
  }
  def getPhases(Is: Array[Int], Qs: Array[Int]): Array[Double] = {
    (Is zip Qs).map { case (i, q) =>
      Math.atan2(q + this.offsetQ, i + this.offsetI)
    }
  }
  def interpretPhases(Is: Array[Int], Qs: Array[Int]): Array[Boolean] = {
    require(Is.length == Qs.length, "Is and Qs must be of the same shape!")
    //System.out.println("interpretPhases: channel " + channel + " crit phase: " + criticalPhase[channel]);
    val phases = getPhases(Is, Qs)
    if (reverseCriticalPhase) {
      phases.map(_ < criticalPhase)
    } else {
      phases.map(_ > criticalPhase)
    }
  }

  def setToDemodulate(channel: Int): Unit = {
    require(channel <= MAX_CHANNELS, s"ADC demod channel must be <= $MAX_CHANNELS")
    this.mode = AdcMode.DEMODULATE
    this._demodChannel = channel
  }
  def setToAverage(): Unit = {
    this.mode = AdcMode.AVERAGE
  }

  override def startDelay(): Int = {
    this.getFpgaModel().getStartDelay()
  }

  override def setStartDelay(startDelay: Int): Unit = {
    this.getFpgaModel().setStartDelay(startDelay)
  }

  // these are passthroughs to the config object. in most cases we do have to check that
  // we are in the proper mode (average vs demod)
  def setFilterFunction(filterFunction: String, stretchLen: Int, stretchAt: Int): Unit = {
    require(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setFilterFunction to be valid.")
    this.filterFunction = filterFunction
    this.stretchLen = stretchLen
    this.stretchAt = stretchAt
  }
  def setTrigMagnitude(ampSin: Int, ampCos: Int): Unit = {
    require(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setTrigMagnitude to be valid.")
    require(ampSin > -1 && ampSin <= TRIG_AMP && ampCos > -1 && ampCos <= TRIG_AMP,
        s"Trig Amplitudes must be 0-255 for channel '$name'")
    this.ampSin = ampSin
    this.ampCos = ampCos
  }
  def setPhase(dPhi: Int, phi0: Int): Unit = {
    require(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setPhase to be valid.")
    //Preconditions.checkArgument(phi0 >= 0 && phi0 < (int)Math.pow(2, LOOKUP_ACCUMULATOR_BITS),
    //"phi0 must be between 0 and 2^%s", LOOKUP_ACCUMULATOR_BITS);
    this.dPhi = dPhi
    this.phi0 = phi0
  }
  def setPhase(frequency: Double, phase: Double): Unit = {
    require(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setPhase to be valid.")
    require(phase >= -Math.PI && phase <= Math.PI, "Phase must be between -pi and pi")
    val dPhi = Math.floor(frequency * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) * DEMOD_TIME_STEP * Math.pow(10, -9.0)).toInt
    val phi0 = (phase * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) / (2 * Math.PI)).toInt
    setPhase(dPhi, phi0)
  }

  //
  // For ADC build 7
  //
  def setTriggerTable(data: Data): Unit = {
    this.triggerTable = data
  }
  def setMixerTable(data: Data): Unit = {
    this.mixerTable = data
  }

  override def clearConfig(): Unit = {
    this.criticalPhase = 0
    this.dPhi = 0
    this.phi0 = 0
    this.filterFunction = ""
    this.stretchAt = -1
    this.stretchLen = -1
    this.ampSin = -1
    this.ampCos = -1
    this.reverseCriticalPhase = false
    this.offsetI = 0
    this.offsetQ = 0
    this.triggerTable = null
    this.mixerTable = null
  }

  override def demodChannel: Int = {
    this._demodChannel
  }

  def reverseCriticalPhase(reverse: Boolean): Unit = {
    this.reverseCriticalPhase = reverse
  }

  def setIqOffset(offsetI: Int, offsetQ: Int): Unit = {
    this.offsetI = offsetI
    this.offsetQ = offsetQ
  }

  def getOffsets(): (Int, Int) = {
    (offsetI, offsetQ)
  }

}
