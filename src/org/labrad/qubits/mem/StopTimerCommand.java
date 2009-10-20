package org.labrad.qubits.mem;

public class StopTimerCommand implements MemoryCommand {
  private StopTimerCommand() {}

  private static final StopTimerCommand INSTANCE = new StopTimerCommand();

  public static StopTimerCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0x400001};
  }
}
