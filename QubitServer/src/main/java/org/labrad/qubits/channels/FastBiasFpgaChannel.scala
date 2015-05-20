package org.labrad.qubits.channels;

import com.google.common.base.Preconditions;
import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.FastBias;

/**
 * Created by pomalley on 3/10/2015.
 * FastBias control via FPGA.
 */

public class FastBiasFpgaChannel extends FastBiasChannel implements FpgaChannel {

  FpgaModelDac fpga;
  DacBoard board;

  public FastBiasFpgaChannel(String name) {
    super(name);
  }

  public void setFastBias(FastBias fb) {
    this.fb = fb;
  }

  public FastBias getFastBias() {
    return fb;
  }

  public void setBiasChannel(DcRackFiberId channel) {
    this.fbChannel = channel;
  }

  public void setExperiment(Experiment expt) {
    this.expt = expt;
  }

  public Experiment getExperiment() {
    return expt;
  }

  public void setFpgaModel(FpgaModel fpga) {
    Preconditions.checkArgument(fpga instanceof FpgaModelDac,
            "FastBias '%s' requires an FpgaModelDac.", getName());
    this.fpga = (FpgaModelDac)fpga;
  }

  public FpgaModelDac getFpgaModel() {
    return fpga;
  }

  public void setDacBoard(DacBoard board) {
    this.board = board;
  }

  public DacBoard getDacBoard() {
    return board;
  }

  public DcRackFiberId getDcFiberId() {
    return fbChannel;
  }

  public DacFiberId getFiberId() {
    return fb.getFiber(fbChannel);
  }

  @Override
  public String getName() {
    return name;
  }

  public void clearConfig() {
    // nothing to do here
  }
}
