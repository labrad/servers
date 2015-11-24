package org.labrad.qubits.config

import org.labrad.data._
import org.labrad.qubits.channels.PreampChannel

object PreampConfig {
  val highPassFilters = Map(
    "DC" -> 0,
    "3300" -> 1,
    "1000" -> 2,
    "330" -> 3,
    "100" -> 4,
    "33" -> 5,
    "10" -> 6,
    "3.3" -> 7
  )

  val lowPassFilters = Map(
    "0" -> 0,
    "0.22" -> 1,
    "0.5" -> 2,
    "1" -> 3,
    "2.2" -> 4,
    "5" -> 5,
    "10" -> 6,
    "22" -> 7
  )
}

case class PreampConfig(offset: Long, polarity: Boolean, highPassName: String, lowPassName: String) {

  import PreampConfig._

  val highPass = highPassFilters.get(highPassName).getOrElse {
    sys.error(s"Invalid high-pass filter value '$highPassName'. Must be one of ${highPassFilters.keys.mkString(",")}")
  }
  val lowPass = lowPassFilters.get(lowPassName).getOrElse {
    sys.error(s"Invalid low-pass filter value '$lowPassName'.  Must be one of ${lowPassFilters.keys.mkString(",")}")
  }

  def getSetupPacket(ch: PreampChannel): SetupPacket = {
    val chName = ch.getPreampBoard().name
    val linkNameEnd = chName.indexOf("Preamp") - 1
    val linkName = chName.substring(0, linkNameEnd)
    val cardId = (chName.substring(linkNameEnd + "Preamp".length() + 2)).toLong

    val settings = Seq(
      "Connect" -> Str(linkName),
      "Select Card" -> UInt(cardId),
      "Register" -> Cluster(
        Str(ch.getPreampChannel.toString.toUpperCase),
        Cluster(UInt(highPass), UInt(lowPass), UInt(if (polarity) 1 else 0), UInt(offset))
      ),
      "Disconnect" -> Data.NONE
    )

    val state = s"${ch.getPreampBoard.name}${ch.getPreampChannel}: offset=$offset polarity=$polarity highPass=$highPass lowPass=$lowPass"

    SetupPacket(state, settings)
  }
}
