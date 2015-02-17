package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum FastBiasProperties {
	GAIN("gain");
	
  private final String name;
  private static final Map<String, FastBiasProperties> map = Maps.newHashMap();

  FastBiasProperties(String name) {
    this.name = name;
  }

  public String toString() {
    return name;
  }

  static {
    for (FastBiasProperties id : values()) {
      map.put(id.name, id);
    }
  }

  public static FastBiasProperties fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid bias command '%s'", name);
    return map.get(key);
  }
}
