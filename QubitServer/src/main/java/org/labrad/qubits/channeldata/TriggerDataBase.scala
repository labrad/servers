package org.labrad.qubits.channeldata;

import org.labrad.qubits.channels.TriggerChannel;

public abstract class TriggerDataBase implements TriggerData {

  private TriggerChannel channel;

  public void setChannel(TriggerChannel channel) {
    this.channel = channel;
  }

  public TriggerChannel getChannel() {
    return channel;
  }
}
