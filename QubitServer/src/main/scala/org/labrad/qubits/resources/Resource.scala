package org.labrad.qubits.resources

import org.labrad.data._
import org.labrad.qubits.Constants
import org.labrad.qubits.enums.DeviceType

trait Resource {
  def name: String
}

object Resource {
  /**
   * Create a resource of the given type.
   * @param type
   * @param name
   * @return
   */
  def create(
    devType: DeviceType,
    name: String,
    properties: Seq[Data],
    adcBuildNums: Map[String, String],
    dacBuildNums: Map[String, String],
    adcBuildProps: Map[String, Map[String, Long]],
    dacBuildProps: Map[String, Map[String, Long]]
  ): Resource = {
    import DeviceType._
    devType match {
      case UWAVEBOARD =>
        val build = dacBuildNums.getOrElse(name, Constants.DEFAULT_DAC_BUILD)
        val props = dacBuildProps.getOrElse(
            Constants.BUILD_INFO_DAC_PREFIX + build,
            Constants.DEFAULT_DAC_PROPERTIES)
        MicrowaveBoard.create(name, build, props)

      case ANALOGBOARD =>
        val build = dacBuildNums.getOrElse(name, Constants.DEFAULT_DAC_BUILD)
        val props = dacBuildProps.getOrElse(
            Constants.BUILD_INFO_DAC_PREFIX + build,
            Constants.DEFAULT_DAC_PROPERTIES)
        AnalogBoard.create(name, build, props)

      case ADCBOARD =>
        val build = adcBuildNums.getOrElse(name, Constants.DEFAULT_ADC_BUILD)
        val props = adcBuildProps.getOrElse(
            Constants.BUILD_INFO_ADC_PREFIX + build,
            Constants.DEFAULT_ADC_PROPERTIES)
        AdcBoard.create(name, build, props)

      case FASTBIAS => FastBias.create(name, properties)
      case PREAMP => PreampBoard.create(name)
      case UWAVESRC => MicrowaveSource.create(name)
    }
  }
}
