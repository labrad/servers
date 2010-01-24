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
   * Maximum number of reps that can be run in one go
   */
  public static final long MAX_REPS = 65520;
  
  /*
   * Servers we need to talk to
   */
  public static final String ANRITSU_SERVER = "Anritsu Server";
  public static final String DC_RACK_SERVER = "DC Rack";
  public static final String GHZ_DAC_SERVER = "GHz DACs";
}
