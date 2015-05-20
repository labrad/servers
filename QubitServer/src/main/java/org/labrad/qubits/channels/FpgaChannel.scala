package org.labrad.qubits.channels;

import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.resources.DacBoard;

/**
 * Created by pomalley on 3/10/2015.
 * Channel interface for channels with an FPGA (e.g. not FastBias over serial).
 */
public interface FpgaChannel extends Channel {

  public DacBoard getDacBoard();

  public void setFpgaModel(FpgaModel fpga);
  public FpgaModel getFpgaModel();

}
