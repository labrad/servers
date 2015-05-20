package org.labrad.qubits.resources;


public class MicrowaveBoard extends DacBoard {
  private MicrowaveSource uwaveSrc = null;

  public static MicrowaveBoard create(String name) {
    MicrowaveBoard board = new MicrowaveBoard(name);
    return board;
  }

  public MicrowaveBoard(String name) {
    super(name);
  }

  public void setMicrowaveSource(MicrowaveSource uwaves) {
    this.uwaveSrc = uwaves;
  }

  public MicrowaveSource getMicrowaveSource() {
    return uwaveSrc;
  }
}
