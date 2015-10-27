package org.labrad.qubits

object Constants {
  /*
   * Minimum delay (in microseconds) after sending a command to the DC Rack
   */
  val DEFAULT_BIAS_DELAY = 4.3

  /*
   * Length of AutoTrigger pulse in nanoseconds
   */
  val AUTOTRIGGER_PULSE_LENGTH = 16

  /*
   * Maximum number of reps that can be run in one go.
   *
   * Must fit into a two byte field in the packet sent to the DACs.
   */
  val MAX_REPS = 65535

  /*
   * Servers we need to talk to
   */
  val REGISTRY_SERVER = "Registry"
  val HITTITE_SERVER = "Hittite T2100 Server"
  val ANRITSU_SERVER = "Anritsu Server"
  val DC_RACK_SERVER = "DC Rack Server"
  val GHZ_FPGA_SERVER = "GHz FPGAs"

  /*
   * Registry information
   */
  val WIRING_PATH = Array("", "Servers", "Qubit Server", "Wiring")
  val WIRING_KEY = "wiring"
  // ([(Type, Name)...],[((GHz board id,chan),(DC board id,chan)),...],[(uwave board id, microwave source id)])
  val WIRING_TYPE = "*(ss), *((ss)(ss)), *(ss)"

  val BUILD_INFO_PATH = Array("", "Servers", "GHz FPGAs")
  val BUILD_INFO_ADC_PREFIX = "adcBuild"
  val BUILD_INFO_DAC_PREFIX = "dacBuild"

  val DEFAULT_ADC_BUILD = "1"
  val DEFAULT_ADC_PROPERTIES: Map[String, Long] = Map(
    "DEMOD_CHANNELS" -> 4,
    "DEMOD_CHANNELS_PER_PACKET" -> 11,
    "DEMOD_PACKET_LEN" -> 46,
    "DEMOD_TIME_STEP" -> 2,
    "AVERAGE_PACKETS" -> 32,
    "AVERAGE_PACKET_LEN" -> 1024,
    "TRIG_AMP" -> 255,
    "LOOKUP_TABLE_LEN" -> 256,
    "FILTER_LEN" -> 4096,
    "SRAM_WRITE_DERPS" -> 9,
    "SRAM_WRITE_PKT_LEN" -> 1024,
    "LOOKUP_ACCUMULATOR_BITS" -> 16
  )

  val DEFAULT_DAC_BUILD = "5"
  val DEFAULT_DAC_PROPERTIES: Map[String, Long] = Map(
    "SRAM_LEN" -> 10240,
    "SRAM_PAGE_LEN" -> 5120,
    "SRAM_DELAY_LEN" -> 1024,
    "SRAM_BLOCK0_LEN" -> 8192,
    "SRAM_BLOCK1_LEN" -> 2048,
    "SRAM_WRITE_PKT_LEN" -> 256
  )
}
