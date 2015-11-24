package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.IqChannel

abstract class IqDataBase extends IqData {

  private var channel: IqChannel = _

  @volatile private var _isDeconvolved = false

  override def setChannel(channel: IqChannel): Unit = {
    this.channel = channel
  }

  protected def getChannel(): IqChannel = {
    channel
  }

  /**
   * Whether this bit of analog data has been deconvolved.
   */
  def isDeconvolved(): Boolean = {
    _isDeconvolved
  }

  override def invalidate(): Unit = {
    setDeconvolved(false)
  }

  private[channeldata] def setDeconvolved(isDeconvolved: Boolean): Unit = {
    _isDeconvolved = isDeconvolved
  }
}
