package org.labrad.qubits.mem;

import org.labrad.qubits.FpgaModelDac;

public class StartTimerCommand implements MemoryCommand {
  private StartTimerCommand() {}

  private static final StartTimerCommand INSTANCE = new StartTimerCommand();

  public static StartTimerCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0x400000};
  }
  public double getTime_us(FpgaModelDac dac) {
    return FpgaModelDac.clocksToMicroseconds(1);
  }
}
