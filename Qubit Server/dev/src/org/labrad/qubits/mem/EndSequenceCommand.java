package org.labrad.qubits.mem;

import org.labrad.qubits.FpgaModelDac;

public class EndSequenceCommand implements MemoryCommand {
  private EndSequenceCommand() {}

  private static final EndSequenceCommand INSTANCE = new EndSequenceCommand();

  public static EndSequenceCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0xF00000};
  }
  public double getTime_us(FpgaModelDac dac) {
    return FpgaModelDac.clocksToMicroseconds(1);
  }
}
