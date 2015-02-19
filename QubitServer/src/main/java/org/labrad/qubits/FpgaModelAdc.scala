package org.labrad.qubits

import org.labrad.data.Data
import org.labrad.qubits.channels.AdcChannel
import org.labrad.qubits.resources.AdcBoard
import org.labrad.qubits.resources.DacBoard
import scala.collection.mutable


object FpgaModelAdc {
  val ACQUISITION_TIME_US = 16.384
  val START_DELAY_UNIT_NS = 4
}

class FpgaModelAdc(board: AdcBoard, expt: Experiment) extends FpgaModel {

  import FpgaModelAdc._

  private val channels = mutable.Buffer.empty[AdcChannel]

  def setChannel(c: AdcChannel) {
    if (!channels.contains(c))
      channels += c
  }

  def getChannel(): AdcChannel = {
    sys.error("getChannel() called for FpgaModelAdc! Bad!")
  }

  override def getDacBoard(): DacBoard = {
    board
  }

  override def name: String = board.name

  //
  // Start Delay - pomalley 5/4/2011
  //
  private var startDelay = -1

  def setStartDelay(startDelay: Int): Unit = {
    this.startDelay = startDelay
  }

  def getStartDelay(): Int = {
    this.startDelay
  }

  override def getSequenceLength_us(): Double = {
    var t_us = this.startDelay * START_DELAY_UNIT_NS / 1000.0
    t_us += ACQUISITION_TIME_US
    t_us
  }

  override def getSequenceLengthPostSRAM_us(): Double = {
    getSequenceLength_us()
  }

  def packets: Seq[(String, Data)] = {
    // first we configure the "global" ADC properties, while checking to see if they were set more than once
    // across the different channels
    // then we set the "local" properties of each demod channel
    if (channels.isEmpty)
      return Nil

    // this is double counting but it doesn't matter
    for (ch1 <- channels; ch2 <- channels) ch1.reconcile(ch2)

    channels(0).globalPackets ++ channels.flatMap(_.localPackets)
  }
}
