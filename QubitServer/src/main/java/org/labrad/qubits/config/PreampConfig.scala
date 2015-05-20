package org.labrad.qubits.config

import org.labrad.data.Data
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
    val chName = ch.getPreampBoard().getName()
    val linkNameEnd = chName.indexOf("Preamp") - 1
    val linkName = chName.substring(0, linkNameEnd)
    val cardId = (chName.substring(linkNameEnd + "Preamp".length() + 2)).toLong

    val data = Data.ofType("(ss)(sw)(s(s(wwww)))(s)")
    data.get(0).setString("Connect", 0).setString(linkName, 1)
    data.get(1).setString("Select Card", 0).setWord(cardId, 1)
    data.get(2).setString("Register", 0).setString(ch.getPreampChannel().toString().toUpperCase(), 1, 0)
    .setWord(highPass, 1, 1, 0)
    .setWord(lowPass, 1, 1, 1)
    .setWord(if (polarity) 1L else 0L, 1, 1, 2)
    .setWord(offset, 1, 1, 3)
    data.get(3).setString("Disconnect", 0)

    val state = s"${ch.getPreampBoard.getName}${ch.getPreampChannel}: offset=$offset polarity=$polarity highPass=$highPass lowPass=$lowPass"

    new SetupPacket(state, data)
  }
}
