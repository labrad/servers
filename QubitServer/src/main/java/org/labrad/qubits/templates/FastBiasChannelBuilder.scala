package org.labrad.qubits.templates;

import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.FastBiasChannel;
import org.labrad.qubits.channels.FastBiasFpgaChannel;
import org.labrad.qubits.channels.FastBiasSerialChannel;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.resources.FastBias;
import org.labrad.qubits.resources.Resources;

import java.util.List;

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
    // TODO: check FPGA name or DC rack card in the wiring
    String boardName = params.get(0); // either e.g. "Vince DAC 11" (board name) or "9" (card number)
    String channel = params.get(1);
    FastBiasChannel fb;
    if (boardName.contains("FastBias")) {
      fb = new FastBiasFpgaChannel(name);
      FastBias board = resources.get(boardName, FastBias.class);
      fb.setFastBias(board);
      fb.setBiasChannel(DcRackFiberId.fromString(channel));
      ((FastBiasFpgaChannel)fb).setDacBoard(board.getDacBoard(DcRackFiberId.fromString(channel)));
    } else {
      fb = new FastBiasSerialChannel(name);
      ((FastBiasSerialChannel)fb).setDCRackCard(Integer.valueOf(boardName));
      fb.setBiasChannel(DcRackFiberId.fromString(channel));
    }
    return fb;
  }
}
