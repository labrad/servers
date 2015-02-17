package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.qubits.enums.ChannelType;
import org.labrad.qubits.resources.Resources;

public class ChannelBuilders {
  /**
   * Build a channel template from a LabRAD data object.
   * @param template
   * @return
   */
  public static ChannelBuilder fromData(Data template, Resources resources) {
    String name = template.get(0).getString();
    String typeName = template.get(1, 0).getString();
    ChannelType type = ChannelType.fromString(typeName);
    List<String> params = template.get(1, 1).getStringList();

    switch (type) {
      case ANALOG: return new AnalogChannelBuilder(name, params, resources);
      case IQ: return new IqChannelBuilder(name, params, resources);
      case TRIGGER: return new TriggerChannelBuilder(name, params, resources);
      case FASTBIAS: return new FastBiasChannelBuilder(name, params, resources);
      case PREAMP: return new PreampChannelBuilder(name, params, resources);
      case ADC: return new AdcChannelBuilder(name, params, resources);
      default: throw new RuntimeException("Unknown channel type: " + type);
    }
  }
}
