package org.labrad.qubits;

import java.util.List;

import org.labrad.data.Request;
import org.labrad.qubits.channels.AdcChannel;
import org.labrad.qubits.config.AdcBaseConfig;
import org.labrad.qubits.resources.AdcBoard;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;

public class FpgaModelAdc implements FpgaModel {

	List<AdcChannel> channels = Lists.newArrayList();
	AdcBoard board;
	Experiment expt;
	
	public FpgaModelAdc(AdcBoard board, Experiment expt) {
		this.board = board;
		this.expt = expt;
		
	}
	
	public void setChannel(AdcChannel c) {
		if (!channels.contains(c))
			channels.add(c);
	}
	public AdcChannel getChannel() {
		Preconditions.checkArgument(false, "getChannel() called for FpgaModelAdc! Bad!");
		return null;
	}
	
	@Override
	public DacBoard getDacBoard() {
		return board;
	}

	@Override
	public String getName() {
		return board.getName();
	}

	public void addPackets(Request runRequest) {
		for (AdcChannel ch : channels) {
			AdcBaseConfig conf = ch.getConfig();
			Preconditions.checkState(conf != null, "ADC channel '%s' was not configured!", ch.getName());
			conf.addPackets(runRequest);
		}
	}

	
}
