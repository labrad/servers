package org.labrad.qubits.mem;

public class NoopCommand implements MemoryCommand {
  private NoopCommand() {}

  private static final NoopCommand INSTANCE = new NoopCommand();

  public static NoopCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0x000000};
  }
}
