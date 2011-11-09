/**
 * 
 */
package org.labrad.qubits.channels;

import java.util.List;
import java.util.Locale;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelAdc;
import org.labrad.qubits.config.AdcAverageConfig;
import org.labrad.qubits.config.AdcBaseConfig;
import org.labrad.qubits.config.AdcDemodConfig;
import org.labrad.qubits.enums.AdcMode;
import org.labrad.qubits.resources.AdcBoard;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;

/**
 * This channel represents a connection to an ADC in demodulation mode.
 * 
 * @author pomalley
 *
 */
public class AdcChannel implements Channel, TimingChannel, StartDelayChannel {
	
	AdcMode mode = AdcMode.UNSET;
	
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
	public AdcBoard getDacBoard() {
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
	
	//
	// Critical phase functions
	//
	
	public void setCriticalPhase(double criticalPhase) {
		Preconditions.checkState(mode == AdcMode.AVERAGE, "Single Critical Phase only valid for average mode.");
		((AdcAverageConfig)config).setCriticalPhase(criticalPhase);
	}
	public void setCriticalPhase(int demodIndex, double criticalPhase) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Set critical phase by index only valid for demod mode.");
		((AdcDemodConfig)config).setCriticalPhase(demodIndex, criticalPhase);
	}
	public void setCriticalPhase(double[] criticalPhases) {
		Preconditions.checkState(mode == AdcMode.DEMODULATE, "Set all critical phases only valid for demod mode.");
		((AdcDemodConfig)config).setCriticalPhases(criticalPhases);
	}
	public boolean[] interpretPhases(int[] is, int[] is2, int subChannel) {
		return config.interpretPhases(is, is2, subChannel);
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
		if (mode != this.mode) {
			this.mode = mode;
			this.clearConfig();
			switch (mode) {
			case DEMODULATE:
				this.config = new AdcDemodConfig(this.name, this.board.getBuildProperties());
				break;
			case AVERAGE:
				this.config = new AdcAverageConfig(this.name, this.board.getBuildProperties());
				break;
			}
		}
	}
	
	/**
	 * @return a list of all active demod channels, or -1 if in average mode.
	 */
	public List<Integer> getActiveChannels() {
		List<Integer> l = Lists.newArrayList();
		if (this.mode == AdcMode.AVERAGE)
			l.add(-1);
		else if (this.mode == AdcMode.DEMODULATE) {
			boolean[] usage = ((AdcDemodConfig)this.config).getChannelUsage();
			for (int i = 0; i < usage.length; i++)
				if (usage[i])
					l.add(i);
		}
		return l;
	}
	
	// these are passthroughs to the config object. in most cases we do have to check that
	// we are in the proper mode (average vs demod)
	@Override
	public void setStartDelay(int startDelay)
	{
		config.setStartDelay(startDelay);
	}
	@Override
	public int getStartDelay() {
		return config.getStartDelay();
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
