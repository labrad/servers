package org.labrad.qubits.channeldata;

import org.labrad.qubits.channels.IqChannel;


public interface IqData extends Deconvolvable {
  public void setChannel(IqChannel channel);
  public int[] getDeconvolvedI();
  public int[] getDeconvolvedQ();
  public void checkLength(int expected);
}
