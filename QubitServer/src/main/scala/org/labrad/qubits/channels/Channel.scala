package org.labrad.qubits.channels

import org.labrad.qubits.Experiment
import org.labrad.qubits.enums._
import org.labrad.qubits.resources._

object Channel {
  /**
   * Construct a channel of some type from the channel definition.
   */
  def apply(name: String, typeName: String, params: Seq[String], resources: Resources): Channel = {
    val chanType = ChannelType.fromString(typeName)

    chanType match {
      case ChannelType.ANALOG =>
        val Seq(boardName, dacId) = params
        val board = resources.get[DacBoard](boardName)
        val id = DacAnalogId.fromString(dacId)
        new AnalogChannel(name, board, id)

      case ChannelType.IQ =>
        val Seq(boardName) = params
        val board = resources.get[MicrowaveBoard](boardName)
        new IqChannel(name, board)

      case ChannelType.TRIGGER =>
        val Seq(boardName, triggerId) = params
        val board = resources.get[DacBoard](boardName)
        val id = DacTriggerId.fromString(triggerId)
        new TriggerChannel(name, board, id)

      case ChannelType.FASTBIAS =>
        val Seq(boardName, channel) = params
        if (boardName.contains("FastBias")) {
          val board = resources.get[FastBias](boardName)
          val fiberId = DcRackFiberId.fromString(channel)
          val dacBoard = board.getDacBoard(fiberId)
          new FastBiasFpgaChannel(name, dacBoard, fiberId)
        } else {
          val rackCard = boardName.toInt
          val fiberId = DcRackFiberId.fromString(channel)
          new FastBiasSerialChannel(name, rackCard, fiberId)
        }

      case ChannelType.PREAMP =>
        val Seq(boardName, channel) = params
        val board = resources.get[PreampBoard](boardName)
        val fiberId = DcRackFiberId.fromString(channel)
        new PreampChannel(name, board, fiberId)

      case ChannelType.ADC =>
        val Seq(boardName) = params
        val board = resources.get[AdcBoard](boardName)
        new AdcChannel(name, board)
    }
  }
}

/**
 * "Channels represent the various signal generation and measurement capabilities that are needed in a
 * particular experiment(IQ, Analog or FastBias, for example), and are assigned names by the user."
 *
 * In the {@link Device} class, for example, a channel connects a physical device to an experimental parameter.
 *
 * @author maffoo
 */
trait Channel {
  def name: String

  def setExperiment(expt: Experiment): Unit
  def getExperiment(): Experiment

  def clearConfig(): Unit
}
