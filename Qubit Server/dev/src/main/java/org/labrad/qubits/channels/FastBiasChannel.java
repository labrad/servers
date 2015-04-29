package org.labrad.qubits.channels;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.FastBias;

public abstract class FastBiasChannel implements FiberChannel {

  String name;
  Experiment expt = null;
  FastBias fb = null;
  DcRackFiberId fbChannel;

  public FastBiasChannel(String name) {
    this.name = name;
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
