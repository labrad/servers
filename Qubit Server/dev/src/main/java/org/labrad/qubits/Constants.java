package org.labrad.qubits;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.labrad.data.Data;

import com.google.common.collect.Lists;

public class Constants {
  /*
   * Minimum delay (in microseconds) after sending a command to the DC Rack
   */
  public static final double DEFAULT_BIAS_DELAY = 4.3;

  /*
   * Length of AutoTrigger pulse in nanoseconds
   */
  public static final int AUTOTRIGGER_PULSE_LENGTH = 16;

  /*
   * Maximum number of reps that can be run in one go.
   * 
   * This number is determined by two factors, first the number
   * of reps must fit into a two byte field in the packet that
   * is sent to the DACs, and second it must be a multiple of 30,
   * since timing results are sent back in groups of 30.
   */
  public static final long MAX_REPS = 65535; // No longer has to be a multiple of 30 ERJ
  //public static final long MAX_REPS = 300;
  /*
   * Servers we need to talk to
   */
  public static final String REGISTRY_SERVER = "Registry";
  public static final String HITTITE_SERVER = "Hittite T2100 Server";
  public static final String ANRITSU_SERVER = "Anritsu Server";
  public static final String DC_RACK_SERVER = "DC Rack Server";
  public static final String GHZ_DAC_SERVER = "GHz FPGAs";

  /*
   * Registry information
   */
  public static final String[] WIRING_PATH = {"", "Servers", "Qubit Server", "Wiring"};
  public static final String WIRING_KEY = "wiring";
  // ([(Type, Name)...],[((GHz board id,chan),(DC board id,chan)),...],[(uwave board id, microwave source id)])
  public static final String WIRING_TYPE = "*(ss), *((ss)(ss)), *(ss)";
  //public static final String WIRING_TYPE = "*(ss?), *((ss)(ss)), *(ss)";
  public static final String[] BUILD_INFO_PATH = {"", "Servers", "GHz FPGAs"};
  public static final String DEFAULT_ADC_PROPERTIES = "[('DEMOD_CHANNELS', 4), ('DEMOD_CHANNELS_PER_PACKET', 11), ('DEMOD_PACKET_LEN', 46), ('DEMOD_TIME_STEP', 2), ('AVERAGE_PACKETS', 32), ('AVERAGE_PACKET_LEN', 1024), ('TRIG_AMP', 255), ('LOOKUP_TABLE_LEN', 256), ('FILTER_LEN', 4096), ('SRAM_WRITE_DERPS', 9), ('SRAM_WRITE_PKT_LEN', 1024), ('LOOKUP_ACCUMULATOR_BITS', 16)]";
  public static final String DEFAULT_DAC_PROPERTIES = "[('SRAM_LEN', 10240), ('SRAM_PAGE_LEN', 5120), ('SRAM_DELAY_LEN', 1024), ('SRAM_BLOCK0_LEN', 8192), ('SRAM_BLOCK1_LEN', 2048), ('SRAM_WRITE_PKT_LEN', 256)]";

  public static final Data PROCESS_PROPERTIES(String rawData) {
    List<Data> l = Lists.newArrayList();
    Pattern p = Pattern.compile(".*?\\('(.+?)',\\s*(\\d+?)\\)");	// remember when reading this to reduce all \\ to \
    Matcher m = p.matcher(rawData);
    while (m.find()) {
      // group 1 is the name, group 2 is the number
      Data d = Data.clusterOf(Data.valueOf(m.group(1)), Data.valueOf(new Long(m.group(2))));
      l.add(d);
    }
    return Data.listOf(l);
  }

  public static final Data DEFAULT_ADC_PROPERTIES_DATA = PROCESS_PROPERTIES(DEFAULT_ADC_PROPERTIES);
  public static final Data DEFAULT_DAC_PROPERTIES_DATA = PROCESS_PROPERTIES(DEFAULT_DAC_PROPERTIES);
}
