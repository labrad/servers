/**
 * 
 */
package org.labrad.qubits.channels;

import java.util.Locale;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelAdc;
import org.labrad.qubits.config.AdcBaseConfig;
import org.labrad.qubits.config.AdcDemodConfig;
import org.labrad.qubits.resources.AdcBoard;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.base.Preconditions;

/**
 * This channel represents a connection to an ADC in demodulation mode.
 * 
 * @author pomalley
 *
 */
public class AdcChannel implements Channel, TimingChannel {

	/**
	 * AdcMode: either demodulate or average.
	 * @author pomalley
	 *
	 */
	public enum AdcMode {
		DEMODULATE("demodulate"),
		AVERAGE("average");
		
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
	
	AdcMode mode = AdcMode.DEMODULATE;
	
	String name = null;
	Experiment expt = null;
	AdcBoard board = null;
	FpgaModelAdc fpga = null;

	AdcBaseConfig config = null;
	

	public AdcChannel(String name) {
		this.name = name;
	}
	
	public void setAdcBoard(AdcBoard board) {
		this.board = board;
	}

	@Override
	public DacBoard getDacBoard() {
		return board;
	}


	@Override
	public Experiment getExperiment() {
		return expt;
	}

	@Override
	public FpgaModelAdc getFpgaModel() {
		return fpga;
	}

	@Override
	public String getName() {
		return name;
	}

	@Override
	public void setExperiment(Experiment expt) {
		this.expt = expt;
	}

	@Override
	public void setFpgaModel(FpgaModel fpga) {
		Preconditions.checkArgument(fpga instanceof FpgaModelAdc,
				"AdcChannel '%s' requires ADC board.", getName());
		this.fpga = (FpgaModelAdc) fpga;
		this.fpga.setChannel(this);
	}
	
	/**
	 * This should clear the configuration. 
	 */
	@Override
	public void clearConfig() {
		config = null;
	}
	
	public AdcBaseConfig getConfig() {
		return config;
	}
	
	public void setMode(String mode) {
		setMode(AdcMode.valueOf(mode.toUpperCase(Locale.ENGLISH)));
		// we use Locale.ENGLISH because goddamit I want this code to work if we go to russia or some shit.
	}
	public void setMode(AdcMode mode) {
		//System.out.println(mode);
		if (mode != this.mode || config == null) {
			this.mode = mode;
			this.clearConfig();
			switch (mode) {
			case DEMODULATE:
				this.config = new AdcDemodConfig();
				break;
			case AVERAGE:
				// TODO: add averaging mode
				this.config = null;
				break;
			}
		}
	}
	
	// these are passthroughs to the config object. in most cases we do have to check that
	// we are in the proper mode (average vs demod)
	public void setStartDelay(int startDelay)
	{
		config.setStartDelay(startDelay);
	}
	public void setFilterFunction(String filterFunction, int stretchLen, int stretchAt) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setFilterFunction to be valid.");
		((AdcDemodConfig)config).setFilterFunction(filterFunction, stretchLen, stretchAt);		
	}
	public void setTrigMagnitude(int channel, int ampSin, int ampCos) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setTrigMagnitude to be valid.");
		((AdcDemodConfig)config).setTrigMagnitude(channel, ampSin, ampCos);
	}
	public void setPhase(int channel, int dPhi, int phi0) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setPhase to be valid.");
		((AdcDemodConfig)config).setPhase(channel, dPhi, phi0);
	}
	public void setPhase(int channel, double frequency, double phase) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for setPhase to be valid.");
		((AdcDemodConfig)config).setPhase(channel, frequency, phase);
	}
	public void turnChannelOn(int channel) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for turnChannelOn to be valid.");
		((AdcDemodConfig)config).turnChannelOn(channel);
	}
	public void turnChannelOff(int channel) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for turnChannelOff to be valid.");
		((AdcDemodConfig)config).turnChannelOff(channel);
	}
	public boolean[] getChannelUsage(int channel) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Channel must be in demodulate mode for getChannelUsage to be valid.");
		return ((AdcDemodConfig)config).getChannelUsage();
	}
}
