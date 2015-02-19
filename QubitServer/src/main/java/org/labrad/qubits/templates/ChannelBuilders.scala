package org.labrad.qubits.templates

import org.labrad.data._
import org.labrad.qubits.enums.ChannelType
import org.labrad.qubits.resources.Resources

object ChannelBuilders {
  /**
   * Build a channel template from a LabRAD data object.
   * @param template
   * @return
   */
  def fromData(template: Data, resources: Resources): ChannelBuilder = {
    import ChannelType._

    val (name, (typeName, params)) = template.get[(String, (String, Seq[String]))]
    val chanType = ChannelType.fromString(typeName)

    chanType match {
      case ANALOG => new AnalogChannelBuilder(name, params, resources)
      case IQ => new IqChannelBuilder(name, params, resources)
      case TRIGGER => new TriggerChannelBuilder(name, params, resources)
      case FASTBIAS => new FastBiasChannelBuilder(name, params, resources)
      case PREAMP => new PreampChannelBuilder(name, params, resources)
      case ADC => new AdcChannelBuilder(name, params, resources)
    }
  }
}
