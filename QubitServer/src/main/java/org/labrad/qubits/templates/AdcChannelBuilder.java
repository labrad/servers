package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.channels.AdcChannel;
import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.resources.AdcBoard;
import org.labrad.qubits.resources.Resources;

public class AdcChannelBuilder extends ChannelBuilderBase {
  private final String name;
  private final List<String> params;
  private final Resources resources;

  public AdcChannelBuilder(String name, List<String> params, Resources resources) {
    this.name = name;
    this.params = params;
    this.resources = resources;
  }

  @Override
  public Channel build() {
    String boardName = params.get(0);
    AdcBoard board = resources.get(boardName, AdcBoard.class);
    AdcChannel adc = new AdcChannel(name, board);
    return adc;
  }

}
