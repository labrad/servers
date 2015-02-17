package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum DacTriggerId {
  S0("s0", 28),
  S1("s1", 29),
  S2("s2", 30),
  S3("s3", 31);

  private String name;
  private int shift;
  private static final Map<String, DacTriggerId> map = Maps.newHashMap();

  DacTriggerId(String name, int shift) {
    this.name = name;
    this.shift = shift;
  }

  public String toString() {
    return name;
  }

  public int getShift() {
    return shift;
  }

  static {
    for (DacTriggerId id : values()) {
      map.put(id.name, id);
    }
  }

  public static DacTriggerId fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid trigger id '%s'", name);
    return map.get(key);
  }
}
