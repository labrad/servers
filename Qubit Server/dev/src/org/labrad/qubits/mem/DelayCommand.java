package org.labrad.qubits.mem;

import java.util.ArrayList;
import java.util.List;

import org.labrad.qubits.FpgaModelDac;

public class DelayCommand implements MemoryCommand {
  private int cycles;

  public DelayCommand(int cycles) {
    this.cycles = cycles;
  }

  public void setDelay(int cycles) {
    this.cycles = cycles;
  }
  public int getDelay() {
    return this.cycles;
  }
  public double getTime_us(FpgaModelDac dac) {
    return FpgaModelDac.clocksToMicroseconds(this.cycles);
  }

  public long[] getBits() {
    int left = cycles;
    List<Long> seq = new ArrayList<Long>();
    while (left > 0x0FFFFF) {
      seq.add(Long.valueOf(0x3FFFFF));
      left -= 0x0FFFFF;
    }
    seq.add(Long.valueOf(0x300000 + left));
    long[] bits = new long[seq.size()];
    for (int i = 0; i < seq.size(); i++) {
      bits[i] = seq.get(i);
    }
    return bits;
  }
}
