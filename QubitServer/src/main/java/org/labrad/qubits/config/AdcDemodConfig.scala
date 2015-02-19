package org.labrad.qubits.config

import org.labrad.data._

/**
 * This holds the configuration info for an ADC in demod mode.
 *
 * It is held by an AdcChannel object. The global parameters are
 * start delay and filter function. The per-channel parameters are the
 * demod phase ((freq or steps/cycle) and (phase or offset steps))
 * and the trigger magnitude (sine amp and cosine amp, each a byte).
 *
 * Note that this is a little different from the way that config objects
 * are normally done in this server. Normally the configs are for other servers
 * (e.g. microwave source) and are sent out as part of the GHz FPGA server's "setup packets".
 * Here the config is for a device on the GHz FPGA server and is sent as part of the main
 * run request.
 *
 * @author pomalley
 *
 */
class AdcDemodConfig(name: String, buildProperties: Map[String, Long]) extends AdcBaseConfig(name, buildProperties) {

  val MAX_CHANNELS = buildProperties("DEMOD_CHANNELS").toInt
  val DEMOD_CHANNELS_PER_PACKET = buildProperties("DEMOD_CHANNELS_PER_PACKET").toInt
  val TRIG_AMP = buildProperties("TRIG_AMP").toInt
  // see fpga server documentation on the "ADC Demod Phase" setting for an explanation of the two below.
  val LOOKUP_ACCUMULATOR_BITS = buildProperties("LOOKUP_ACCUMULATOR_BITS").toInt
  val DEMOD_TIME_STEP = buildProperties("DEMOD_TIME_STEP").toInt // in ns

  /**
   * Each byte is the weight for a 4 ns interval.
   * A single value can be repeated for a stretch in the middle.
   * How long to repeat for is specified by stretchLen,
   * and where to start repeating by stretchAt.
   */
  private var filterFunction = ""
  private var stretchLen = -1
  private var stretchAt = -1

  /**
   * Each channel has a dPhi, the number of addresses to step through
   * per time sample.
   */
  private var dPhi = Array.fill[Int](MAX_CHANNELS) { -1 }

  /**
   * phi0 is where on the sine lookup table to start (again for each channel)
   */
  private var phi0 = Array.fill[Int](MAX_CHANNELS) { -1 }

  /**
   * ampSin and ampCos are the magnitude of the cos and sin functions of a given channel
   */
  private var ampSin = Array.fill[Int](MAX_CHANNELS) { -1 }
  private val ampCos = Array.fill[Int](MAX_CHANNELS) { -1 }

  /**
   * keeps a list of what channels we're using
   */
  private var inUse = Array.ofDim[Boolean](MAX_CHANNELS)

  /**
   * critical phase for each demod channel
   */
  private var criticalPhase = Array.ofDim[Double](MAX_CHANNELS)

  /*
  private int numChannelsInUse() {
    int n = 0;
    for (boolean b : inUse)
      if (b)
        n++;
  return n;
  }*/

  /**
   * @return array of booleans telling use state of each channel.
   */
  def getChannelUsage(): Array[Boolean] = {
    inUse
  }

  def turnChannelOn(channel: Int): Unit = {
    require(channel <= MAX_CHANNELS, s"channel must be <= $MAX_CHANNELS")
    inUse(channel) = true
  }

  def turnChannelOff(channel: Int): Unit = {
    require(channel <= MAX_CHANNELS, s"channel must be <= $MAX_CHANNELS")
    inUse(channel) = false
  }

  /**
   * Set all critical phases.
   * @param criticalPhases
   */
  def setCriticalPhases(criticalPhases: Array[Double]): Unit = {
    require(criticalPhases.length == MAX_CHANNELS, "Number of critical phases must = number of channels")
    for (i <- criticalPhases.indices) {
      require(criticalPhases(i) >= 0.0 && criticalPhases(i) <= 2*Math.PI,
          "Critical phases must be between 0 and 2PI")
      this.criticalPhase(i) = criticalPhases(i)
    }
  }

  /**
   * Set a single critical phase.
   * @param channelIndex
   * @param criticalPhase
   */
  def setCriticalPhase(channelIndex: Int, criticalPhase: Double): Unit = {
    require(channelIndex >= 0 && channelIndex < MAX_CHANNELS, "channelIndex must be >= 0 and < MAX_CHANNELS")
    require(criticalPhase >= -Math.PI && criticalPhase <= Math.PI, "Critical phase must be between -PI and PI")
    this.criticalPhase(channelIndex) = criticalPhase
  }

  /**
   * Converts Is and Qs into booleans using the previously defined critical phase.
   * @param Is
   * @param Qs
   * @return
   */
  def interpretPhases(Is: Array[Int], Qs: Array[Int], channel: Int): Array[Boolean] = {
    require(Is.length == Qs.length, "Is and Qs must be of the same shape!")
    require(inUse(channel), s"Interpret phases on channel $channel -- channel not turned on!")
    //System.out.println("interpretPhases: channel " + channel + " crit phase: " + criticalPhase[channel]);
    (Is zip Qs).map { case (i, q) =>
      Math.atan2(q, i) > criticalPhase(channel)
    }
  }

  def setFilterFunction(filterFunction: String, stretchLen: Int, stretchAt: Int): Unit = {
    this.filterFunction = filterFunction
    this.stretchLen = stretchLen
    this.stretchAt = stretchAt
  }

  def setTrigMagnitude(channel: Int, ampSin: Int, ampCos: Int): Unit = {
    require(channel <= MAX_CHANNELS, s"channel must be <= $MAX_CHANNELS")
    require(ampSin > -1 && ampSin <= TRIG_AMP && ampCos > -1 && ampCos <= TRIG_AMP,
        s"Trig Amplitudes must be 0-255 for channel '$name'")
    this.inUse(channel) = true
    this.ampSin(channel) = ampSin
    this.ampCos(channel) = ampCos
  }

  /**
   * sets the demodulation phase
   * @param channel the channel index
   * @param dPhi the number of addresses to step through per time step
   * @param phi0 the initial offset
   */
  def setPhase(channel: Int, dPhi: Int, phi0: Int): Unit = {
    require(channel <= MAX_CHANNELS, s"channel must be <= $MAX_CHANNELS")
    //Preconditions.checkArgument(phi0 >= 0 && phi0 < (int)Math.pow(2, LOOKUP_ACCUMULATOR_BITS),
    //"phi0 must be between 0 and 2^%s", LOOKUP_ACCUMULATOR_BITS);
    inUse(channel) = true
    this.dPhi(channel) = dPhi
    this.phi0(channel) = phi0
  }

  /**
   * sets the demodulation phase.
   * @param channel the channel index
   * @param frequency in Hz. it is converted in this function.
   * @param phase of the offset IN RADIANS. it is converted to an address.
   */
  def setPhase(channel: Int, frequency: Double, phase: Double): Unit = {
    require(phase >= -Math.PI && phase <= Math.PI, "Phase must be between -pi and pi")
    val dPhi = Math.floor(frequency * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) * DEMOD_TIME_STEP * Math.pow(10, -9.0)).toInt
    val phi0 = (phase * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) / (2 * Math.PI)).toInt
    setPhase(channel, dPhi, phi0)
  }

  /**
   * In the demod case, the following packets are added:
   * ADC Run Mode
   * Start Delay
   * ADC Filter Func
   * for each channel: ADC Demod Phase
   *                   ADC Trig Magnitude
   * @param runRequest The request to which we add the packets.
   * @author pomalley
   */
  def packets: Seq[(String, Data)] = {
    // check that the user has set everything that needs to be set
    require(startDelay > -1, s"ADC Start Delay not set for channel '$name'")
    require(stretchLen > -1 && stretchAt > -1, s"ADC Filter Func not set for channel '$name'")
    require(inUse.contains(true), s"No demod channels activated for channel '$name'")
    for (i <- 0 until MAX_CHANNELS) {
      if (inUse(i)) {
        //Preconditions.checkState(phi0[i] > -1, " %s on channel '%s'", i, this.channelName);
        require(ampSin(i) > -1 && ampCos(i) > -1, s"ADC Trig Magnitude not set on activated demod channel $i on channel $name")
      }
    }
    // add the requests
    val records = Seq.newBuilder[(String, Data)]
    records += "ADC Run Mode" -> Str("demodulate")
    records += "Start Delay" -> UInt(startDelay)
    records += "ADC Filter Func" -> Cluster(Str(filterFunction), UInt(stretchLen), UInt(stretchAt))
    for (i <- 0 until MAX_CHANNELS) {
      if (inUse(i)) {
        records += "ADC Demod Phase" -> Cluster(UInt(i), Integer(dPhi(i)), Integer(phi0(i)))
        records += "ADC Trig Magnitude" -> Cluster(UInt(i), UInt(ampSin(i)), UInt(ampCos(i)))
      }
    }
    records.result
  }
}
