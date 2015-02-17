package org.labrad.qubits.resources;

import java.util.Set;

import com.google.common.collect.Sets;

public class MicrowaveSource implements Resource {
  String name;
  String server;
  String device;

  Set<MicrowaveBoard> boards = Sets.newHashSet();

  public static MicrowaveSource create(String name) {
    MicrowaveSource board = new MicrowaveSource(name);
    return board;
  }

  public MicrowaveSource(String name) {
    this.name = name;
    this.device = name;
  }

  public void addMicrowaveBoard(MicrowaveBoard board) {
    boards.add(board);
  }

  public Set<MicrowaveBoard> getMicrowaveBoards() {
    return boards;
  }

  public String getName() {
    return name;
  }

  public String getServer() {
    return server;
  }

  public String getDevice() {
    return device;
  }
}
