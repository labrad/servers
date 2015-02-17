package org.labrad.qubits.enums;


/**
 * AdcMode: either demodulate or average.
 * @author pomalley
 *
 */
public enum AdcMode {
  DEMODULATE("demodulate"),
  AVERAGE("average"),
  UNSET("unset"); // for before it is set by user

  /**
   * string must be the string that is passed to the GHz FPGA server
   * to specify which run mode to put the ADC in.
   */
  private final String string;

  AdcMode(String str) {
    string = str;
  }

  @Override
  public String toString() {
    return string;
  }
}