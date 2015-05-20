package org.labrad.qubits.resources;

import java.util.Map;

import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public class PreampBoard implements BiasBoard {
  private String name;
  private Map<DcRackFiberId, DacBoard> dacBoards = Maps.newHashMap();
  private Map<DcRackFiberId, DacFiberId> dacFibers = Maps.newHashMap();

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
}
