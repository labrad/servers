package org.labrad.qubits.jumptable

import java.util.ArrayList
import org.labrad.data.Data
import org.labrad.data.Request

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
    val argClone = argument.clone()
    // TODO: type check the name and argument
    if (name == "CYCLE") {
      val args = argClone.getClusterAsList()
      require(args.size() == 4, s"Cycle must have 4 arguments; currently has $args")
      if (countersUsed == NUM_COUNTERS) {
        sys.error("More than 4 counters used in jump table.")
      } else {
        counters(countersUsed) = argClone.get(3).getWord()
        argClone.get(3).setWord(countersUsed)
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
  def addPackets(runRequest: Request): Unit = {
    runRequest.add("Jump Table Clear")
    runRequest.add("Jump Table Set Counters", Data.valueOf(counters))
    for (i <- 0 until entryNames.size()) {
      runRequest.add("Jump Table Add Entry", Data.valueOf(entryNames.get(i)), entryArguments.get(i))
    }
  }
}
