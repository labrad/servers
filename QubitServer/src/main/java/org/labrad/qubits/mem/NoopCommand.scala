package org.labrad.qubits.mem;

import org.labrad.qubits.FpgaModelDac;

public class NoopCommand implements MemoryCommand {
  private NoopCommand() {}

  private static final NoopCommand INSTANCE = new NoopCommand();

  public static NoopCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0x000000};
  }
  public double getTime_us(FpgaModelDac dac) {
    return FpgaModelDac.clocksToMicroseconds(1);
  }
}
