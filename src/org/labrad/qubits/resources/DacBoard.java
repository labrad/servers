package org.labrad.qubits.resources;

import java.util.Map;

import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;

import com.google.common.collect.Maps;

public abstract class DacBoard implements Resource {
  private String name;

  private Map<DacFiberId, BiasBoard> fibers = Maps.newHashMap();
  private Map<DacFiberId, DcRackFiberId> fiberChannels = Maps.newHashMap();

  public DacBoard(String name) {
    this.name = name;
  }

  public String getName() {
    return name;
  }

  public void setFiber(DacFiberId fiber, BiasBoard board, DcRackFiberId channel) {
    fibers.put(fiber, board);
    fiberChannels.put(fiber, channel);
  }
}
