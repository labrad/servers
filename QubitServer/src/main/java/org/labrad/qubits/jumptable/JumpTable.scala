package org.labrad.qubits.jumptable

import java.util.ArrayList
import org.labrad.data._

/**
 * Created by pomalley on 2/13/15.
 *
 * Basic logic for the jump table.
 */
object JumpTable {
  val NUM_COUNTERS = 4 // TODO: get num counters from hardware
}

class JumpTable {
  import JumpTable._

  private val entryNames = new ArrayList[String]
  private val entryArguments = new ArrayList[Data]
  private var counters = Array[Long](0, 0, 0, 0)  // TODO: get from hardware
  private var countersUsed = 0

  /**
   * Emtpy this jump table.
   */
  def clear(): Unit = {
    entryNames.clear()
    entryArguments.clear()
    counters = Array(0, 0, 0, 0)  // TODO: get from hardware
  }

  def addEntry(name: String, argument: Data): Unit = {
    val argClone = Data.copy(argument, Data(argument.t))
    // TODO: type check the name and argument
    if (name == "CYCLE") {
      require(argClone.clusterSize == 4, s"Cycle must have 4 arguments; currently has $argClone")
      if (countersUsed == NUM_COUNTERS) {
        sys.error("More than 4 counters used in jump table.")
      } else {
        counters(countersUsed) = argClone(3).getUInt
        argClone(3).setUInt(countersUsed)
        countersUsed += 1
      }
    }

    entryNames.add(name)
    entryArguments.add(argClone)
  }

  /**
   * Add jump table packets to the FPGA server.
   * The correct DAC must already have been selected.
   * @param runRequest request to the GHz FPGA server
   */
  def packets: Seq[(String, Data)] = {
    val builder = Seq.newBuilder[(String, Data)]
    builder += "Jump Table Clear" -> Data.NONE
    builder += "Jump Table Set Counters" -> Arr(counters)
    for (i <- 0 until entryNames.size()) {
      builder += "Jump Table Add Entry" -> Cluster(Str(entryNames.get(i)), entryArguments.get(i))
    }
    builder.result
  }
}
