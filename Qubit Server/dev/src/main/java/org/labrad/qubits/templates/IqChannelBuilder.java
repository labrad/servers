package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.resources.MicrowaveBoard;
import org.labrad.qubits.resources.MicrowaveSource;
import org.labrad.qubits.resources.Resources;

public class IqChannelBuilder extends ChannelBuilderBase {
  private final String name;
  private final List<String> params;
  private final Resources resources;

  public IqChannelBuilder(String name, List<String> params, Resources resources) {
    this.name = name;
    this.params = params;
    this.resources = resources;
  }

  public Channel build() {
    String boardName = params.get(0);
    IqChannel iq = new IqChannel(name);
    MicrowaveBoard board = resources.get(boardName, MicrowaveBoard.class);
    iq.setDacBoard(board);
    MicrowaveSource src = board.getMicrowaveSource();
    iq.setMicrowaveSource(src);
    return iq;
  }
}
