package org.labrad.qubits.templates

import org.labrad.data.Data
import org.labrad.qubits.enums.ChannelType
import org.labrad.qubits.resources.Resources
import scala.collection.JavaConverters._

object ChannelBuilders {
  /**
   * Build a channel template from a LabRAD data object.
   * @param template
   * @return
   */
  def fromData(template: Data, resources: Resources): ChannelBuilder = {
    import ChannelType._

    val name = template.get(0).getString()
    val typeName = template.get(1, 0).getString()
    val chanType = ChannelType.fromString(typeName)
    val params = template.get(1, 1).getStringList().asScala.toSeq

    chanType match {
      case ANALOG => new AnalogChannelBuilder(name, params, resources)
      case IQ => new IqChannelBuilder(name, params, resources)
      case TRIGGER => new TriggerChannelBuilder(name, params, resources)
      case FASTBIAS => new FastBiasChannelBuilder(name, params, resources)
      case PREAMP => new PreampChannelBuilder(name, params, resources)
      case ADC => new AdcChannelBuilder(name, params, resources)
      case _ => sys.error(s"Unknown channel type: $chanType")
    }
  }
}
