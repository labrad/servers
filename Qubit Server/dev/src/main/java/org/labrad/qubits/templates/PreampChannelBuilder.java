package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.PreampChannel;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.PreampBoard;
import org.labrad.qubits.resources.Resources;

public class PreampChannelBuilder extends ChannelBuilderBase {
  private final String name;
  private final List<String> params;
  private final Resources resources;

  public PreampChannelBuilder(String name, List<String> params, Resources resources) {
    this.name = name;
    this.params = params;
    this.resources = resources;
  }

  public Channel build() {
    String boardName = params.get(0);
    String channel = params.get(1);
    PreampChannel pc = new PreampChannel(name);
    PreampBoard board = resources.get(boardName, PreampBoard.class);
    pc.setPreampBoard(board);
    pc.setPreampChannel(DcRackFiberId.fromString(channel));
    // look up the dacBoard on the other end and connect to it
    pc.setDacBoard(board.getDacBoard(DcRackFiberId.fromString(channel)));
    return pc;
  }
}