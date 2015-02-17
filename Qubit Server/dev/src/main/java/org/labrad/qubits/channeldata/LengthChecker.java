package org.labrad.qubits.channeldata;

import com.google.common.base.Preconditions;

public class LengthChecker {
  public static void checkLengths(int actual, int expected) {
    Preconditions.checkArgument(actual == expected,
        "Incorrect SRAM block length: expected %s but got %s", expected, actual);
  }
}
