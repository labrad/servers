package org.labrad.qubits.resources;


public class AnalogBoard extends DacBoard {

  public static AnalogBoard create(String name) {
    AnalogBoard board = new AnalogBoard(name);
    return board;
  }

  public AnalogBoard(String name) {
    super(name);
  }
}
