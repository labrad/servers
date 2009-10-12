package org.labrad.qubits;

public class Constants {
	/*
	 * Minimum delay (in microseconds) after sending a command to the DC Rack
	 */
	public final static double DEFAULT_BIAS_DELAY = 4.3;

	/*
	 * Length of AutoTrigger pulse in nanoseconds
	 */
	public final static int AUTOTRIGGER_PULSE_LENGTH = 16;
	
	/*
	 * Servers we need to talk to
	 */
	public final static String ANRITSU_SERVER = "Anritsu Server";
	public final static String DC_RACK_SERVER = "DC Rack";
	public final static String GHZ_DAC_SERVER = "GHz DACs";
}
