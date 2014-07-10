package org.labrad.qubits.channeldata;

import org.labrad.qubits.channels.TriggerChannel;

public interface TriggerData {
  public void setChannel(TriggerChannel channel);
  public boolean[] get();
  public void checkLength(int expected);
}
