package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.TriggerChannel;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.Resources;

public class TriggerChannelBuilder extends ChannelBuilderBase {
  private final String name;
  private final List<String> params;
  private final Resources resources;

  public TriggerChannelBuilder(String name, List<String> params, Resources resources) {
    this.name = name;
    this.params = params;
    this.resources = resources;
  }

  public Channel build() {
    String boardName = params.get(0);
    String triggerId = params.get(1);
    TriggerChannel tc = new TriggerChannel(name);
    DacBoard board = resources.get(boardName, DacBoard.class);
    tc.setDacBoard(board);
    tc.setTriggerId(DacTriggerId.fromString(triggerId));
    return tc;
  }
}