package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.enums.DacAnalogId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.Resources;

public class AnalogChannelBuilder implements ChannelBuilder {
  private final String name;
  private final List<String> params;
  private final Resources resources;

  public AnalogChannelBuilder(String name, List<String> params, Resources resources) {
    this.name = name;
    this.params = params;
    this.resources = resources;
  }

  public Channel build() {
    String boardName = params.get(0);
    String dacId = params.get(1);
    AnalogChannel ch = new AnalogChannel(name);
    DacBoard board = resources.get(boardName, DacBoard.class);
    ch.setDacBoard(board);
    ch.setDacId(DacAnalogId.fromString(dacId));
    return ch;
  }
}
