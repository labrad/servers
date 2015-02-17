package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum ChannelType {
  ANALOG("analog"),
  IQ("iq"),
  TRIGGER("trigger"),
  PREAMP("preamp"),
  FASTBIAS("fastbias"),
  ADC("adc");

  private final String name;
  private static final Map<String, ChannelType> map = Maps.newHashMap();

  ChannelType(String name) {
    this.name = name;
  }

  public String toString() {
    return name;
  }

  static {
    for (ChannelType id : values()) {
      map.put(id.name, id);
    }
  }

  public static ChannelType fromString(String name) {
    String key = name.toLowerCase();
    Preconditions.checkArgument(map.containsKey(key),
        "Invalid bias channel id '%s'", name);
    return map.get(key);
  }
}
