package org.labrad.qubits.channels;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.config.PreampConfig;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.PreampBoard;

public class PreampChannel implements FiberChannel {

	String name;
	Experiment expt = null;
	DacBoard board = null;
	FpgaModel fpga = null;
	PreampBoard preampBoard;
	DcRackFiberId preampChannel;
	PreampConfig config = null;

	public PreampChannel(String name) {
		this.name = name;
		clearConfig();
	}
	
	@Override
	public String getName() {
		return name;
	}

	public void setPreampBoard(PreampBoard preampBoard) {
		this.preampBoard = preampBoard;
	}

	public PreampBoard getPreampBoard() {
		return preampBoard;
	}

	public void setPreampChannel(DcRackFiberId preampChannel) {
		this.preampChannel = preampChannel;
	}
	
	public DcRackFiberId getPreampChannel() {
		return preampChannel;
	}

	public void setExperiment(Experiment expt) {
		this.expt = expt;
	}
	
	public Experiment getExperiment() {
		return expt;
	}
	
	public void setDacBoard(DacBoard board) {
		this.board = board;
	}
	
	public DacBoard getDacBoard() {
		return board;
	}
	
	public void setFpgaModel(FpgaModel fpga) {
		this.fpga = fpga;
	}
	
	public FpgaModel getFpgaModel() {
		return fpga;
	}
	
	public void startTimer() {
		fpga.startTimer();
	}
	
	public void stopTimer() {
		fpga.stopTimer();
	}
	
	// configuration
	
	public void clearConfig() {
		config = null;
	}
	
	public void setPreampConfig(long offset, boolean polarity, String highPass, String lowPass) {
		config = new PreampConfig(offset, polarity, highPass, lowPass);
	}
	
	public boolean hasPreampConfig() {
		return config != null;
	}
	
	public PreampConfig getPreampConfig() {
		return config;
	}
	
}
