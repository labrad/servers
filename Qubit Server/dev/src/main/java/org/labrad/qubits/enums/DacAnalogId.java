package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum DacAnalogId {
  A("a", 0),
  B("b", 14);

  private final String name;
  private final int shift;
  private static final Map<String, DacAnalogId> map = Maps.newHashMap();

  DacAnalogId(String name, int shift) {
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
    for (DacAnalogId id : values()) {
      map.put(id.name, id);
    }
  }

  public static DacAnalogId fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid dac id '%s'", name);
    return map.get(key);
  }
}
