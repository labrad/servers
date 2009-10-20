package org.labrad.qubits.mem;

import org.labrad.qubits.channels.FastBiasChannel;
import org.labrad.qubits.enums.BiasCommandType;

public class FastBiasCommands {
  public static SendFiberCommand get(BiasCommandType type, FastBiasChannel fb, double v) {
    switch (type) {
      case DAC0: return setDac0(fb, v);
      case DAC0_NOSELECT: return setDac0NoSelect(fb, v);
      case DAC1: return setDac1Fast(fb, v);
      case DAC1_SLOW: return setDac1Slow(fb, v);
      default: throw new RuntimeException("Unknown bias command type: " + type);
    }
  }

  private static SendFiberCommand setDac0(FastBiasChannel fb, double v) {
    int level = (int)(v/2500.0 * 0xFFFF) & 0xFFFF;
    int bits = 0x00000 + (level << 3);
    return makeCommand(fb, bits);
  }

  private static SendFiberCommand setDac0NoSelect(FastBiasChannel fb, double v) {
    int level = (int)(v/2500.0 * 0xFFFF) & 0xFFFF;
    int bits = 0x00004 + (level << 3);
    return makeCommand(fb, bits);
  }

  private static SendFiberCommand setDac1Fast(FastBiasChannel fb, double v) {
    int level = (int)((v+2500.0)/5000.0 * 0xFFFF) & 0xFFFF;
    int bits = 0x80000 + (level << 3);
    return makeCommand(fb, bits);
  }

  private static SendFiberCommand setDac1Slow(FastBiasChannel fb, double v) {
    int level = (int)((v+2500.0)/5000.0 * 0xFFFF) & 0xFFFF;
    int bits = 0x80004 + (level << 3);
    return makeCommand(fb, bits);
  }

  private static SendFiberCommand makeCommand(FastBiasChannel fb, int bits) {
    return new SendFiberCommand(fb.getFiberId(), bits);
  }
}
