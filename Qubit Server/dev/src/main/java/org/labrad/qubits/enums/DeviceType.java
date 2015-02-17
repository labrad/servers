package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum DeviceType {
  ANALOGBOARD("analogboard"),
  UWAVEBOARD("microwaveboard"),
  UWAVESRC("microwavesource"),
  PREAMP("preamp"),
  FASTBIAS("fastbias"),
  ADCBOARD("adcboard");

  private final String name;
  private static final Map<String, DeviceType> map = Maps.newHashMap();

  DeviceType(String name) {
    this.name = name;
  }

  public String toString() {
    return name;
  }

  static {
    for (DeviceType id : values()) {
      map.put(id.name, id);
    }
  }

  public static DeviceType fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid bias channel id '%s'", name);
    return map.get(key);
  }
}
