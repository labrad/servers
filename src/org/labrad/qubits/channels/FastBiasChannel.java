package org.labrad.qubits.channels;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.enums.BiasFiberId;
import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.FastBias;

public class FastBiasChannel implements FiberChannel {

	String name;
	Experiment expt = null;
	FpgaModel fpga = null;
	FastBias fb = null;
	DacBoard board = null;
	BiasFiberId fbChannel;
	
	public FastBiasChannel(String name) {
		this.name = name;
	}
	
	public void setFastBias(FastBias fb) {
		this.fb = fb;
	}
	
	public FastBias getFastBias() {
		return fb;
	}
	
	public void setBiasChannel(BiasFiberId channel) {
		this.fbChannel = channel;
	}
	
	public void setExperiment(Experiment expt) {
		this.expt = expt;
	}
	
	public Experiment getExperiment() {
		return expt;
	}
	
	public void setFpgaModel(FpgaModel fpga) {
		this.fpga = fpga;
	}
	
	public FpgaModel getFpgaModel() {
		return fpga;
	}
	
	public void setDacBoard(DacBoard board) {
		this.board = board;
	}
	
	public DacBoard getDacBoard() {
		return board;
	}
	
	public DacFiberId getFiberId() {
		return fb.getFiber(fbChannel);
	}
	
	@Override
	public String getName() {
		return name;
	}

	public void clearConfig() {
		// nothing to do here
	}
}
