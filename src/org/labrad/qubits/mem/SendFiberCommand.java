package org.labrad.qubits.mem;

import org.labrad.qubits.enums.DacFiberId;

public class SendFiberCommand implements MemoryCommand {
  private DacFiberId channel;
  private int bits;

  public SendFiberCommand(DacFiberId channel, int bits) {
    this.channel = channel;
    this.bits = bits;
  }

  public long[] getBits() {
    int send;
    switch (channel) {
      case FOUT_0: send = 0x100000; break;
      case FOUT_1: send = 0x200000; break;
      default:
        throw new RuntimeException("Invalid DAC fiber id: " + channel);
    }
    return new long[] {send + (bits & 0x0FFFFF)};
  }
}
