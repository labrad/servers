package org.labrad.qubits.channels;

import java.util.Map;

import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelAdc;
import org.labrad.qubits.enums.AdcMode;
import org.labrad.qubits.resources.AdcBoard;

import com.google.common.base.Preconditions;

/**
 * This channel represents a connection to an ADC in demodulation mode.
 *
 * @author pomalley
 *
 */
public class AdcChannel implements Channel, TimingChannel, StartDelayChannel {

  public final int MAX_CHANNELS, DEMOD_CHANNELS_PER_PACKET, TRIG_AMP, LOOKUP_ACCUMULATOR_BITS, DEMOD_TIME_STEP;

  String name = null;
  Experiment expt = null;
  AdcBoard board = null;
  FpgaModelAdc fpga = null;

  // configuration variables
  AdcMode mode = AdcMode.UNSET; // DEMODULATE, AVERAGE, UNSET
  String filterFunction; int stretchLen, stretchAt; // passed to filter function setting
  double criticalPhase; // used to interpret phases (into T/F switches)
  int demodChannel; // which demod channel are we (demod mode only)
  int dPhi, phi0; // passed to "ADC Demod Phase" setting of FPGA server (demod mode only)
  int ampSin, ampCos; // passed to "ADC Trig Magnitude" setting (demod mode only)
  Data triggerTable; // passed to "ADC Trigger Table"
  Data mixerTable; // passed to "ADC Mixer Table"

  private boolean reverseCriticalPhase;

  private int offsetI;

  private int offsetQ;

  public AdcChannel(String name, AdcBoard board) {
    this.name = name;
    this.board = board;
    this.clearConfig();

    Map<String, Long> bp = this.board.getBuildProperties();
    MAX_CHANNELS = bp.get("DEMOD_CHANNELS").intValue();
    DEMOD_CHANNELS_PER_PACKET = bp.get("DEMOD_CHANNELS_PER_PACKET").intValue();
    TRIG_AMP = bp.get("TRIG_AMP").intValue();
    // see fpga server documentation on the "ADC Demod Phase" setting for an explanation of the two below.
    LOOKUP_ACCUMULATOR_BITS = bp.get("LOOKUP_ACCUMULATOR_BITS").intValue();
    DEMOD_TIME_STEP = bp.get("DEMOD_TIME_STEP").intValue(); // in ns
  }

  @Override
  public AdcBoard getDacBoard() {
    return board;
  }

  @Override
  public Experiment getExperiment() {
    return expt;
  }

  @Override
  public FpgaModelAdc getFpgaModel() {
    return fpga;
  }

  @Override
  public String getName() {
    return name;
  }

  @Override
  public void setExperiment(Experiment expt) {
    this.expt = expt;
  }

  @Override
  public void setFpgaModel(FpgaModel fpga) {
    Preconditions.checkArgument(fpga instanceof FpgaModelAdc,
        "AdcChannel '%s' requires ADC board.", getName());
    this.fpga = (FpgaModelAdc) fpga;
    this.fpga.setChannel(this);
  }

  // reconcile this ADC configuration with another one for the same ADC.
  public boolean reconcile(AdcChannel other) {
    if (this.board != other.board)
      return false;
    if (this == other)
      return true;
    Preconditions.checkArgument(this.mode == other.mode,
        "Conflicting modes for ADC board %s", this.board.getName());
    Preconditions.checkArgument(this.getStartDelay() == other.getStartDelay(),
        "Conflicting start delays for ADC board %s", this.board.getName());
    Preconditions.checkArgument(this.triggerTable.pretty().equals(other.triggerTable.pretty()),
        "Conflicting trigger tables for ADC board %s, (this: %s, other, %s)", this.board.getName(), this.triggerTable.pretty(), other.triggerTable.pretty());
    if (this.mode == AdcMode.DEMODULATE) {
      Preconditions.checkArgument(this.filterFunction.equals(other.filterFunction),
          "Conflicting filter functions for ADC board %s", this.board.getName());
      Preconditions.checkArgument(this.stretchAt == other.stretchAt,
          "Conflicting stretchAt parameters for ADC board %s", this.board.getName());
      Preconditions.checkArgument(this.stretchLen == other.stretchLen,
          "Conflicting stretchLen parameters for ADC board %s", this.board.getName());
      Preconditions.checkArgument(this.demodChannel != other.demodChannel,
          "Two ADC Demod channels with same channel number for ADC board %s", this.board.getName());
    } else if (this.mode == AdcMode.AVERAGE) {
      // nothing?
    } else {
      Preconditions.checkArgument(false, "ADC board %s has no mode (avg/demod) set!", this.board.getName());
    }
    return true;
  }

  // add global packets for this ADC board. should only be called on one channel per board!
  public void addGlobalPackets(Request runRequest) {
    if (this.mode == AdcMode.AVERAGE) {
      Preconditions.checkState(getStartDelay() > -1, "ADC Start Delay not set for channel '%s'", this.name);
      runRequest.add("ADC Run Mode", Data.valueOf("average"));
      runRequest.add("Start Delay", Data.valueOf((long)this.getStartDelay()));
      //runRequest.add("ADC Filter Func", Data.valueOf("balhQLIYFGDSVF"), Data.valueOf(42L), Data.valueOf(42L));
    } else if (this.mode == AdcMode.DEMODULATE) {
      Preconditions.checkState(getStartDelay() > -1, "ADC Start Delay not set for channel '%s'", this.name);
      //Preconditions.checkState(stretchLen > -1 && stretchAt > -1, "ADC Filter Func not set for channel '%s'", this.name);
      runRequest.add("ADC Run Mode", Data.valueOf("demodulate"));
      runRequest.add("Start Delay", Data.valueOf((long)this.getStartDelay()));
      //runRequest.add("ADC Filter Func", Data.valueOf(this.filterFunction),
      //Data.valueOf((long)this.stretchLen), Data.valueOf((long)this.stretchAt));
    } else {
      Preconditions.checkArgument(false, "ADC channel %s has no mode (avg/demod) set!", this.name);
    }
    if (this.triggerTable != null) {
      runRequest.add("ADC Trigger Table", this.triggerTable);
    }
  }

  // add local packets. only really applicable for demod mode
  public void addLocalPackets(Request runRequest) {
    /*
    if (this.mode == AdcMode.DEMODULATE) {
      Preconditions.checkState(ampSin > -1 && ampCos > -1, "ADC Trig Magnitude not set on demod channel %s on channel '%s'", this.demodChannel, this.name);
      runRequest.add("ADC Demod Phase", Data.valueOf((long)this.demodChannel), Data.valueOf(dPhi), Data.valueOf(phi0));
      runRequest.add("ADC Trig Magnitude", Data.valueOf((long)this.demodChannel), Data.valueOf((long)ampSin), Data.valueOf((long)ampCos));
    }
    */
    if (this.mixerTable != null) {
      runRequest.add("ADC Mixer Table", Data.valueOf((long)this.demodChannel), this.mixerTable);
    }
  }

  //
  // Critical phase functions
  //

  public void setCriticalPhase(double criticalPhase) {
    Preconditions.checkState(criticalPhase >= -Math.PI && criticalPhase <= Math.PI,
        "Critical phase must be between -PI and PI");
    this.criticalPhase = criticalPhase;
  }
  public double[] getPhases(int[] Is, int []Qs) {
    double[] results = new double[Is.length];
    for (int run = 0; run<Is.length; run++) {
      results[run] = Math.atan2(Qs[run]+this.offsetQ, Is[run]+this.offsetI);
    }
    return results;
  }
  public boolean[] interpretPhases(int[] Is, int[] Qs) {
    Preconditions.checkArgument(Is.length == Qs.length, "Is and Qs must be of the same shape!");
    //System.out.println("interpretPhases: channel " + channel + " crit phase: " + criticalPhase[channel]);
    boolean[] switches = new boolean[Is.length];
    double[] phases = getPhases(Is, Qs);
    for (int run = 0; run < Is.length; run++) {
      if (this.reverseCriticalPhase)
        switches[run] = phases[run] < criticalPhase;
      else
        switches[run] = phases[run] > criticalPhase;
    }
    return switches;
  }

  public void setToDemodulate(int channel) {
    Preconditions.checkArgument(channel <= MAX_CHANNELS, "ADC demod channel must be <= %s", MAX_CHANNELS);
    this.mode = AdcMode.DEMODULATE;
    this.demodChannel = channel;
  }
  public void setToAverage() {
    this.mode = AdcMode.AVERAGE;
  }

  @Override
  public int getStartDelay() {
    return this.getFpgaModel().getStartDelay();
  }

  @Override
  public void setStartDelay(int startDelay) {
    this.getFpgaModel().setStartDelay(startDelay);
  }

  // these are passthroughs to the config object. in most cases we do have to check that
  // we are in the proper mode (average vs demod)
  public void setFilterFunction(String filterFunction, int stretchLen, int stretchAt) {
    Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setFilterFunction to be valid.");
    this.filterFunction = filterFunction;
    this.stretchLen = stretchLen;
    this.stretchAt = stretchAt;
  }
  public void setTrigMagnitude(int ampSin, int ampCos) {
    Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setTrigMagnitude to be valid.");
    Preconditions.checkArgument(ampSin > -1 && ampSin <= TRIG_AMP && ampCos > -1 && ampCos <= TRIG_AMP, 
        "Trig Amplitudes must be 0-255 for channel '%s'", this.name);
    this.ampSin = ampSin;
    this.ampCos = ampCos;
  }
  public void setPhase(int dPhi, int phi0) {
    Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setPhase to be valid.");
    //Preconditions.checkArgument(phi0 >= 0 && phi0 < (int)Math.pow(2, LOOKUP_ACCUMULATOR_BITS),
    //"phi0 must be between 0 and 2^%s", LOOKUP_ACCUMULATOR_BITS);
    this.dPhi = dPhi;
    this.phi0 = phi0;
  }
  public void setPhase(double frequency, double phase) {
    Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setPhase to be valid.");
    Preconditions.checkArgument(phase >= -Math.PI && phase <= Math.PI, "Phase must be between -pi and pi");
    int dPhi = (int)Math.floor(frequency * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) * DEMOD_TIME_STEP * Math.pow(10, -9.0));
    int phi0 = (int)(phase * Math.pow(2, LOOKUP_ACCUMULATOR_BITS) / (2 * Math.PI));
    setPhase(dPhi, phi0); 
  }

  //
  // For ADC build 7
  //
  public void setTriggerTable(Data data) {
    this.triggerTable = data;
  }
  public void setMixerTable(Data data) {
    this.mixerTable = data;
  }

  @Override
  public void clearConfig() {
    this.criticalPhase = this.dPhi = this.phi0 = 0;
    this.filterFunction = "";
    this.stretchAt = this.stretchLen = this.ampSin = this.ampCos = -1;
    this.reverseCriticalPhase = false;
    this.offsetI = 0;
    this.offsetQ = 0;
    this.triggerTable = null;
    this.mixerTable = null;
  }

  @Override
  public int getDemodChannel() {
    return this.demodChannel;
  }

  public void reverseCriticalPhase(boolean reverse) {
    this.reverseCriticalPhase = reverse;
  }

  public void setIqOffset(int offsetI, int offsetQ) {
    this.offsetI = offsetI;
    this.offsetQ = offsetQ;
  }

  public int[] getOffsets() {
    int[] arr = new int[2];
    arr[0] = this.offsetI; arr[1] = this.offsetQ;
    return arr;
  }

}
