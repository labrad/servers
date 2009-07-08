package org.labrad.qubits.resources;

import java.util.Map;

import org.labrad.qubits.enums.BiasFiberId;
import org.labrad.qubits.enums.DacFiberId;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public class PreampBoard implements BiasBoard {
	private String name;
	private Map<BiasFiberId, DacBoard> dacBoards = Maps.newHashMap();
	private Map<BiasFiberId, DacFiberId> dacFibers = Maps.newHashMap();
	
	public static PreampBoard create(String name) {
		PreampBoard board = new PreampBoard(name);
		return board;
	}
	
	public PreampBoard(String name) {
		this.name = name;
	}
	
	public String getName() {
		return name;
	}
	
	public void setDacBoard(BiasFiberId channel, DacBoard board, DacFiberId fiber) {
		dacBoards.put(channel, board);
		dacFibers.put(channel, fiber);
	}
	
	public DacBoard getDacBoard(BiasFiberId channel) {
		Preconditions.checkArgument(dacBoards.containsKey(channel),
				"No DAC board wired to channel '%s' on board '%s'", channel.toString(), name);
		return dacBoards.get(channel);
	}
	
	public DacFiberId getFiber(BiasFiberId channel) {
		Preconditions.checkArgument(dacBoards.containsKey(channel),
				"No DAC board wired to channel '%s' on board '%s'", channel.toString(), name);
		return dacFibers.get(channel);
	}
}
