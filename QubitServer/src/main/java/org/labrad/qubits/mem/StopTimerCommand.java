package org.labrad.qubits.mem;

import org.labrad.qubits.FpgaModelDac;

public class StopTimerCommand implements MemoryCommand {
  private StopTimerCommand() {}

  private static final StopTimerCommand INSTANCE = new StopTimerCommand();

  public static StopTimerCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0x400001};
  }
  public double getTime_us(FpgaModelDac dac) {
    return FpgaModelDac.clocksToMicroseconds(1);
  }
}
