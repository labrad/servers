package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.FastBiasChannel;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.FastBias;
import org.labrad.qubits.resources.Resources;

public class FastBiasChannelBuilder extends ChannelBuilderBase {
  private final String name;
  private final List<String> params;
  private final Resources resources;

  public FastBiasChannelBuilder(String name, List<String> params, Resources resources) {
    this.name = name;
    this.params = params;
    this.resources = resources;
  }

  public Channel build() {
    String boardName = params.get(0);
    String channel = params.get(1);
    FastBiasChannel fb = new FastBiasChannel(name);
    FastBias board = resources.get(boardName, FastBias.class);
    fb.setFastBias(board);
    fb.setBiasChannel(DcRackFiberId.fromString(channel));
    fb.setDacBoard(board.getDacBoard(DcRackFiberId.fromString(channel)));
    return fb;
  }
}
