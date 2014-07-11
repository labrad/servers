package org.labrad.qubits.mem;
import org.labrad.qubits.FpgaModelDac;

public interface MemoryCommand {
  public long[] getBits();
  public double getTime_us(FpgaModelDac dac);
}
