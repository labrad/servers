package org.labrad.qubits.config;


import java.util.Map;

import org.labrad.data.Data;
import org.labrad.data.Request;

import com.google.common.base.Preconditions;

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
public class AdcDemodConfig extends AdcBaseConfig {

  public final int MAX_CHANNELS, DEMOD_CHANNELS_PER_PACKET, TRIG_AMP, LOOKUP_ACCUMULATOR_BITS, DEMOD_TIME_STEP;
  boolean printed = false;
  /**
   * Each byte is the weight for a 4 ns interval.
   * A single value can be repeated for a stretch in the middle.
   * How long to repeat for is specified by stretchLen,
   * and where to start repeating by stretchAt.
   */
  String filterFunction;
  int stretchLen, stretchAt;

  /**
   * Each channel has a dPhi, the number of addresses to step through
   * per time sample.
   */
  int dPhi[];

  /**
   * phi0 is where on the sine lookup table to start (again for each channel)
   */
  int phi0[];

  /**
   * ampSin and ampCos are the magnitude of the cos and sin functions of a given channel
   */
  int ampSin[], ampCos[];

  /**
   * keeps a list of what channels we're using
   */
  boolean inUse[];

  /**
   * critical phase for each demod channel
   */
  double criticalPhase[];

  public AdcDemodConfig(String channelName, Map<String, Long> buildProperties) {
    super(channelName, buildProperties);
    startDelay = -1;
    filterFunction = "";
    stretchLen = -1; stretchAt = -1;

    MAX_CHANNELS = buildProperties.get("DEMOD_CHANNELS").intValue();
    DEMOD_CHANNELS_PER_PACKET = buildProperties.get("DEMOD_CHANNELS_PER_PACKET").intValue();
    TRIG_AMP = buildProperties.get("TRIG_AMP").intValue();
    // see fpga server documentation on the "ADC Demod Phase" setting for an explanation of the two below.
    LOOKUP_ACCUMULATOR_BITS = buildProperties.get("LOOKUP_ACCUMULATOR_BITS").intValue();
    DEMOD_TIME_STEP = buildProperties.get("DEMOD_TIME_STEP").intValue(); // in ns

    dPhi = new int[MAX_CHANNELS];// for (int i : dPhi) i--;
    phi0 = new int[MAX_CHANNELS]; //for (int i : phi0) i--;
    ampSin = new int[MAX_CHANNELS]; for (int i=0; i<MAX_CHANNELS; i++) ampSin[i]=-1;
    ampCos = new int[MAX_CHANNELS]; for (int i=0; i<MAX_CHANNELS; i++) ampCos[i]=-1;
    inUse = new boolean[MAX_CHANNELS];
    criticalPhase = new double[MAX_CHANNELS];
  }

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
  public boolean[] getChannelUsage() {
    return inUse;
  }

  public void turnChannelOn(int channel) {
    Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
    inUse[channel] = true;
  }

  public void turnChannelOff(int channel) {
    Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
    inUse[channel] = false;
  }

  /**
   * Set all critical phases.
   * @param criticalPhases
   */
  public void setCriticalPhases(double[] criticalPhases) {
    Preconditions.checkArgument(criticalPhases.length == MAX_CHANNELS, "Number of critical phases must = number of channels");
    for (int i = 0; i < criticalPhases.length; i++) {
      Preconditions.checkArgument(criticalPhases[i] >= 0.0 && criticalPhases[i] <= 2*Math.PI,
          "Critical phases must be between 0 and 2PI");
      criticalPhase[i] = criticalPhases[i];
    }
  }

  /**
   * Set a single critical phase.
   * @param channelIndex
   * @param criticalPhase
   */
  public void setCriticalPhase(int channelIndex, double criticalPhase) {
    Preconditions.checkArgument(channelIndex >= 0 && channelIndex < MAX_CHANNELS, "channelIndex must be >= 0 and < MAX_CHANNELS");
    Preconditions.checkArgument(criticalPhase >= -Math.PI && criticalPhase <= Math.PI, "Critical phase must be between -PI and PI");
    this.criticalPhase[channelIndex] = criticalPhase;
  }

  /**
   * Converts Is and Qs into booleans using the previously defined critical phase.
   * @param Is
   * @param Qs
   * @return
   */
  @Override
  public boolean[] interpretPhases(int[] Is, int[] Qs, int channel) {
    Preconditions.checkArgument(Is.length == Qs.length, "Is and Qs must be of the same shape!");
    Preconditions.checkArgument(inUse[channel], "Interpret phases on channel %s -- channel not turned on!", channel);
    //System.out.println("interpretPhases: channel " + channel + " crit phase: " + criticalPhase[channel]);
    boolean[] switches = new boolean[Is.length];
    for (int run = 0; run < Is.length; run++) {
      switches[run] = Math.atan2(Qs[run], Is[run]) > criticalPhase[channel];
    }
    return switches;
  }

  public void setFilterFunction(String filterFunction, int stretchLen, int stretchAt) {
    this.filterFunction = filterFunction;
    this.stretchLen = stretchLen;
    this.stretchAt = stretchAt;
  }

  public void setTrigMagnitude(int channel, int ampSin, int ampCos) {
    Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
    Preconditions.checkArgument(ampSin > -1 && ampSin <= TRIG_AMP && ampCos > -1 && ampCos <= TRIG_AMP, 
        "Trig Amplitudes must be 0-255 for channel '%s'", this.channelName);
    this.inUse[channel] = true;
    this.ampSin[channel] = ampSin;
    this.ampCos[channel] = ampCos;
  }

  /**
   * sets the demodulation phase
   * @param channel the channel index
   * @param dPhi the number of addresses to step through per time step
   * @param phi0 the initial offset
   */
  public void setPhase(int channel, int dPhi, int phi0) {
    Preconditions.checkArgument(channel <= MAX_CHANNELS, "channel must be <= %s", MAX_CHANNELS);
    //Preconditions.checkArgument(phi0 >= 0 && phi0 < (int)Math.pow(2, LOOKUP_ACCUMULATOR_BITS),
    //"phi0 must be between 0 and 2^%s", LOOKUP_ACCUMULATOR_BITS);
    inUse[channel] = true;
    this.dPhi[channel] = dPhi;
    this.phi0[channel] = phi0;
  }

  /**
   * sets the demodulation phase.
   * @param channel the channel index
   * @param frequency in Hz. it is converted in this function.
   * @param phase of the offset IN RADIANS. it is converted to an address.
   */
  public void setPhase(int channel, double frequency, double phase) {
    Preconditions.checkArgument(phase >= -Math.PI && phase <= Math.PI, "Phase must be between -pi and pi");
    int dPhi = (int)Math.floor(frequency * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) * DEMOD_TIME_STEP * Math.pow(10, -9.0));
    int phi0 = (int)(phase * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) / (2 * Math.PI));
    setPhase(channel, dPhi, phi0); 
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
  public void addPackets(Request runRequest) {
    // check that the user has set everything that needs to be set
    Preconditions.checkState(startDelay > -1, "ADC Start Delay not set for channel '%s'", this.channelName);
    Preconditions.checkState(stretchLen > -1 && stretchAt > -1, "ADC Filter Func not set for channel '%s'", this.channelName);
    boolean oneFound = false;
    for (int i = 0; i < MAX_CHANNELS; i++) {
      if (inUse[i]) {
        oneFound = true;
        //Preconditions.checkState(phi0[i] > -1, " %s on channel '%s'", i, this.channelName);
        Preconditions.checkState(ampSin[i] > -1 && ampCos[i] > -1, "ADC Trig Magnitude not set on activated demod channel %s on channel '%s'", i, this.channelName);
      }
    }
    Preconditions.checkState(oneFound, "No demod channels activated for channel '%s'", this.channelName);
    // add the requests
    runRequest.add("ADC Run Mode", Data.valueOf("demodulate"));
    runRequest.add("Start Delay", Data.valueOf((long)this.startDelay));
    runRequest.add("ADC Filter Func", Data.valueOf(this.filterFunction),
        Data.valueOf((long)this.stretchLen), Data.valueOf((long)this.stretchAt));
    for (int i = 0; i < MAX_CHANNELS; i++) {
      if (inUse[i]) {
        runRequest.add("ADC Demod Phase", Data.valueOf((long)i), Data.valueOf(dPhi[i]), Data.valueOf(phi0[i]));
        runRequest.add("ADC Trig Magnitude", Data.valueOf((long)i), Data.valueOf((long)ampSin[i]), Data.valueOf((long)ampCos[i]));
      }
    }
  }
}
