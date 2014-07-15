package org.labrad.qubits.resources;

import java.util.List;
import java.util.Map;

import org.labrad.data.Data;
import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public class FastBias implements BiasBoard {
  private String name;
  private Map<DcRackFiberId, DacBoard> dacBoards = Maps.newHashMap();
  private Map<DcRackFiberId, DacFiberId> dacFibers = Maps.newHashMap();
  private Map<DcRackFiberId, Double> gains = Maps.newHashMap();
  
  public static FastBias create(String name, List<Data> properties) {
    FastBias board = new FastBias(name);
    board.setProperties(properties);
    return board;
  }

  public FastBias(String name) {
    this.name = name;
  }

  public String getName() {
    return name;
  }

  public void setDacBoard(DcRackFiberId channel, DacBoard board, DacFiberId fiber) {
    dacBoards.put(channel, board);
    dacFibers.put(channel, fiber);
  }

  public DacBoard getDacBoard(DcRackFiberId channel) {
    Preconditions.checkArgument(dacBoards.containsKey(channel),
        "No DAC board wired to channel '%s' on board '%s'", channel.toString(), name);
    return dacBoards.get(channel);
  }

  public DacFiberId getFiber(DcRackFiberId channel) {
    Preconditions.checkArgument(dacBoards.containsKey(channel),
        "No DAC board wired to channel '%s' on board '%s'", channel.toString(), name);
    return dacFibers.get(channel);
  }
  
  public double getGain(DcRackFiberId channel) {
  	if (gains.containsKey(channel)) {
  		return gains.get(channel);
  	}
  	return 1.0;
  }
  
  private void setProperties(List<Data> properties) {
  	for (Data elem : properties) {
  		String name = elem.get(0).getString();
  		if (name.equals("gain")) {
  			DcRackFiberId[] channels = DcRackFiberId.values();
  			double[] values = elem.get(1).getValueArray();
  			for (int i = 0; i < channels.length; i++) { gains.put(channels[i], values[i]); }
  		}  		
  	}
  }
}
