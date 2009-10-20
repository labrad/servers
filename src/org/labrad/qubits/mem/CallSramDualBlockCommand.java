package org.labrad.qubits.mem;

import com.google.common.base.Preconditions;

public class CallSramDualBlockCommand implements MemoryCommand {
  private String block1, block2;
  private Double delay;

  public CallSramDualBlockCommand(String block1, String block2) {
    this(block1, block2, null);
  }

  public CallSramDualBlockCommand(String block1, String block2, Double delay) {
    this.block1 = block1;
    this.block2 = block2;
    this.delay = delay;
  }

  public String getBlockName1() {
    return block1;
  }

  public String getBlockName2() {
    return block2;
  }

  public double getDelay() {
    Preconditions.checkNotNull(delay, "Dual-block SRAM delay not set!");
    return delay;
  }

  public void setDelay(double delay) {
    this.delay = delay;
  }

  public long[] getBits() {
    // the GHz DACs server handles layout of SRAM for dual block
    return new long[] {0x800000,
                       0xA00000,
                       0xC00000};
  }

}
