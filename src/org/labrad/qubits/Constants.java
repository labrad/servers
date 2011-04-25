package org.labrad.qubits;

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
  public static final long MAX_REPS = 65520;
  
  /*
   * Servers we need to talk to
   */
  public static final String REGISTRY_SERVER = "Registry";
  public static final String ANRITSU_SERVER = "Anritsu Server";
  public static final String DC_RACK_SERVER = "DC Rack";
  public static final String GHZ_DAC_SERVER = "GHz FPGAs";
  
  /*
   * Registry information
   */
  public static final String[] WIRING_PATH = {"", "Servers", "Qubit Server", "Wiring"};
  public static final String WIRING_KEY = "wiring_2";
  // ([(Type, Name)...],[((GHz board id,chan),(DC board id,chan)),...],[(uwave board id, microwave source id)])
  public static final String WIRING_TYPE = "*(ss), *((ss)(ss)), *(ss)";
  //public static final String WIRING_TYPE = "*(ss?), *((ss)(ss)), *(ss)";
}
