package org.labrad.qubits.channels;


import org.labrad.qubits.enums.DcRackFiberId;

public interface FiberChannel extends Channel {

  public DcRackFiberId getDcFiberId();
  public void setBiasChannel(DcRackFiberId channel);
}
