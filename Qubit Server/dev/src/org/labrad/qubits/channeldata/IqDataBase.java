package org.labrad.qubits.channeldata;

import org.labrad.qubits.channels.IqChannel;

public abstract class IqDataBase implements IqData {

  private IqChannel channel;

  private boolean isDeconvolved = false;

  @Override
  public void setChannel(IqChannel channel) {
    this.channel = channel;
  }

  protected IqChannel getChannel() {
    return channel;
  }

  /**
   * Whether this bit of analog data has been deconvolved.
   */
  @Override
  public boolean isDeconvolved() {
    return isDeconvolved;
  }

  @Override
  public void invalidate() {
    isDeconvolved = false;
  }
  
  protected void setDeconvolved(boolean isDeconvolved) {
    this.isDeconvolved = isDeconvolved;
  }
}
