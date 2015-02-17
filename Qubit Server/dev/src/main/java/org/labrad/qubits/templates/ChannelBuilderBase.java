package org.labrad.qubits.templates;

import java.util.List;

import org.labrad.qubits.resources.Resources;

public abstract class ChannelBuilderBase implements ChannelBuilder {
  protected String name;
  protected List<String> params;
  protected Resources resources;

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public void setResources(Resources resources) {
    this.resources = resources;
  }

  public void setParameters(List<String> params) {
    this.params = params;
  }
}
