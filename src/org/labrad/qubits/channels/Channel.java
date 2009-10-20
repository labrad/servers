package org.labrad.qubits.channels;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.resources.DacBoard;

public interface Channel {
  public String getName();

  public DacBoard getDacBoard();

  public void setExperiment(Experiment expt);
  public Experiment getExperiment();

  public void setFpgaModel(FpgaModel fpga);
  public FpgaModel getFpgaModel();

  public void clearConfig();
}
