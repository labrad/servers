package org.labrad.qubits;

import java.util.List;

import org.labrad.data.Request;
import org.labrad.qubits.channels.AdcChannel;
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
		// first we configure the "global" ADC properties, while checking to see if they were set more than once
		// across the different channels
		// then we set the "local" properties of each demod channel
		if (channels.size() == 0)
			return;
		
		// this is double counting but it doesn't matter
		for (AdcChannel ch1 : channels)
			for (AdcChannel ch2 : channels)
				ch1.reconcile(ch2);
		channels.get(0).addGlobalPackets(runRequest);
		for (AdcChannel ch : channels) {
			ch.addLocalPackets(runRequest);
		}
	}

	
}
