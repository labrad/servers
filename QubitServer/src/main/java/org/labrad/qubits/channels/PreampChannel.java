package org.labrad.qubits.channels;

import java.util.Arrays;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.config.PreampConfig;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.PreampBoard;

import com.google.common.base.Preconditions;

public class PreampChannel implements FiberChannel, TimingChannel {

  String name;
  Experiment expt = null;
  DacBoard board = null;
  FpgaModelDac fpga = null;
  PreampBoard preampBoard;
  DcRackFiberId preampChannel;
  PreampConfig config = null;
  long[][] switchIntervals = null;

  public PreampChannel(String name) {
    this.name = name;
    clearConfig();
  }

  @Override
  public String getName() {
    return name;
  }

  public void setPreampBoard(PreampBoard preampBoard) {
    this.preampBoard = preampBoard;
  }

  public PreampBoard getPreampBoard() {
    return preampBoard;
  }

  public void setPreampChannel(DcRackFiberId preampChannel) {
    this.preampChannel = preampChannel;
  }

  public DcRackFiberId getPreampChannel() {
    return preampChannel;
  }

  public void setExperiment(Experiment expt) {
    this.expt = expt;
  }

  public Experiment getExperiment() {
    return expt;
  }

  public void setDacBoard(DacBoard board) {
    this.board = board;
  }

  public DacBoard getDacBoard() {
    return board;
  }

  public void setFpgaModel(FpgaModel fpga) {
    Preconditions.checkArgument(fpga instanceof FpgaModelDac, "Preamp channel's FpgaModel must be FpgaModelDac.");
    this.fpga = (FpgaModelDac)fpga;
  }

  @Override
  public FpgaModelDac getFpgaModel() {
    return fpga;
  }

  public void startTimer() {
    fpga.getMemoryController().startTimer();
  }

  public void stopTimer() {
    fpga.getMemoryController().stopTimer();
  }

  // configuration

  public void clearConfig() {
    config = null;
  }

  public void setPreampConfig(long offset, boolean polarity, String highPass, String lowPass) {
    config = new PreampConfig(offset, polarity, highPass, lowPass);
  }

  public boolean hasPreampConfig() {
    return config != null;
  }

  public PreampConfig getPreampConfig() {
    return config;
  }

  /**
   * Set intervals of time that are to be interpreted as switches.
   * These are converted to FPGA memory cycles before being stored internally.
   * A single timing result will be interpreted as a switch if it lies within
   * any one of these intervals.
   * @param intervals
   */
  public void setSwitchIntervals(double[][] intervals) {
    switchIntervals = new long[intervals.length][];
    for (int i = 0; i < intervals.length; i++) {
      Preconditions.checkArgument(intervals[i].length == 2, "Switch intervals must have length 2");
      long a = FpgaModelDac.microsecondsToClocks(intervals[i][0]);
      long b = FpgaModelDac.microsecondsToClocks(intervals[i][1]);
      switchIntervals[i] = new long[] {Math.min(a, b), Math.max(a, b)};
    }
  }

  /**
   * Convert an array of cycle times to boolean switches for this channel.
   * @param cycles
   * @return
   */
  public boolean[] interpretSwitches(long[] cycles) {
    boolean[] ans = new boolean[cycles.length];
    Arrays.fill(ans, false);
    for (int i = 0; i < switchIntervals.length; i++) {
      for (int j = 0; j < ans.length; j++) {
        ans[j] |= (cycles[j] > switchIntervals[i][0]) && (cycles[j] < switchIntervals[i][1]);
      }
    }
    return ans;
  }

  @Override
  public int getDemodChannel() {
    // this is a bit of a kludge, only applies to ADCs.
    return -1;
  }

  @Override
  public DcRackFiberId getDcFiberId() {
    return this.getPreampChannel();
  }

  @Override
  public void setBiasChannel(DcRackFiberId channel) {
    this.setPreampChannel(channel);
  }
}
