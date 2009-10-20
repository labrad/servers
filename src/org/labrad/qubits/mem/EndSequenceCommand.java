package org.labrad.qubits.mem;

public class EndSequenceCommand implements MemoryCommand {
  private EndSequenceCommand() {}

  private static final EndSequenceCommand INSTANCE = new EndSequenceCommand();

  public static EndSequenceCommand getInstance() {
    return INSTANCE;
  }

  public long[] getBits() {
    return new long[] {0xF00000};
  }
}
