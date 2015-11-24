package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.IqChannel

trait IqData extends Deconvolvable {
  def setChannel(channel: IqChannel): Unit
  def getDeconvolvedI(): Array[Int]
  def getDeconvolvedQ(): Array[Int]
  def checkLength(expected: Int): Unit
}
