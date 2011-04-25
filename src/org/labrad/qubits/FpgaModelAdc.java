package org.labrad.qubits;

import org.labrad.qubits.channels.AdcChannel;
import org.labrad.qubits.resources.AdcBoard;
import org.labrad.qubits.resources.DacBoard;

public class FpgaModelAdc implements FpgaModel {

	AdcChannel channel;
	AdcBoard board;
	Experiment expt;
	
	public FpgaModelAdc(AdcBoard board, Experiment expt) {
		this.board = board;
		this.expt = expt;
		
	}
	
	public void setChannel(AdcChannel c) {
		channel = c;
	}
	public AdcChannel getChannel() {
		return channel;
	}
	
	@Override
	public DacBoard getDacBoard() {
		return board;
	}

	@Override
	public String getName() {
		return board.getName();
	}

	
}
