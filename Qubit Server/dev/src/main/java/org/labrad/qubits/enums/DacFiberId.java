package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum DacFiberId {
  FIN(-1, "in"),
  FOUT_0(0, "out0"),
  FOUT_1(1, "out1");

  private final int id;
  private final String name;
  private static final Map<String, DacFiberId> map = Maps.newHashMap();

  DacFiberId(Integer id, String name) {
    this.id = id;
    this.name = name;
  }

  public int asInt() {
    return id;
  }

  public String toString() {
    return name;
  }

  static {
    for (DacFiberId id : values()) {
      map.put(id.name, id);
    }
  }

  public static DacFiberId fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid dac fiber id '%s'", name);
    return map.get(key);
  }
}
