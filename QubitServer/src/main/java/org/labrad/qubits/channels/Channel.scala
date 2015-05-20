package org.labrad.qubits.channels;

import org.labrad.qubits.Experiment;


/**
 * "Channels represent the various signal generation and measurement capabilities that are needed in a
 * particular experiment(IQ, Analog or FastBias, for example), and are assigned names by the user."
 *
 * In the {@link Device} class, for example, a channel connects a physical device to an experimental parameter.
 *
 * @author maffoo
 */
public interface Channel {
  public String getName();

  public void setExperiment(Experiment expt);
  public Experiment getExperiment();

  public void clearConfig();
}
