package org.labrad.qubits.mem;

public class CallSramCommand implements MemoryCommand {
  private String blockName;	
  private int startAddr, endAddr;

  public CallSramCommand(String name) {
    this.blockName = name;
  }

  public String getBlockName() {
    return blockName;
  }

  public void setStartAddress(int startAddr) {
    this.startAddr = startAddr;
  }

  public void setEndAddress(int endAddr) {
    this.endAddr = endAddr;
  }

  public long[] getBits() {
    return new long[] {0x800000 + (startAddr & 0x0FFFFF),
                       0xA00000 + (endAddr & 0x0FFFFF),
                       0xC00000};
  }

}
