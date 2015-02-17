package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum DcRackFiberId {
  A("a"),
  B("b"),
  C("c"),
  D("d");

  private final String name;
  private static final Map<String, DcRackFiberId> map = Maps.newHashMap();

  DcRackFiberId(String name) {
    this.name = name;
  }

  public String toString() {
    return name;
  }

  static {
    for (DcRackFiberId id : values()) {
      map.put(id.name, id);
    }
  }

  public static DcRackFiberId fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid bias channel id '%s'", name);
    return map.get(key);
  }
}
