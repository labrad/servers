package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

/**
 * Allowed types for memory bias commands (implemented by the FastBias boards).
 * Note that these types are also documented in the Mem Add Bias setting, so
 * changes here should also be made in the docs for that setting.
 */
public enum BiasCommandType {
  DAC0("dac0"),
  DAC0_NOSELECT("dac0noselect"),
  DAC1("dac1"),
  DAC1_SLOW("dac1slow");

  private final String name;
  private static final Map<String, BiasCommandType> map = Maps.newHashMap();

  BiasCommandType(String name) {
    this.name = name;
  }

  public String toString() {
    return name;
  }

  static {
    for (BiasCommandType id : values()) {
      map.put(id.name, id);
    }
  }

  public static BiasCommandType fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid bias command '%s'", name);
    return map.get(key);
  }
}
