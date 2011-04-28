package org.labrad.qubits.resources;

import java.util.List;
import java.util.Map;

import org.labrad.data.Data;
import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;

import com.google.common.collect.Maps;

public abstract class DacBoard implements Resource {
  private String name;

  private Map<DacFiberId, BiasBoard> fibers = Maps.newHashMap();
  private Map<DacFiberId, DcRackFiberId> fiberChannels = Maps.newHashMap();
  
  protected String buildType;		// either 'adcBuild' or 'dacBuild'
  protected String buildNumber;
  protected Map<String, Long> buildProperties = Maps.newHashMap();

  public DacBoard(String name) {
    this.name = name;
    this.buildType = "dacBuild";
  }

  public String getName() {
    return name;
  }
  
  public String getBuildType() {
	  return buildType;
  }
  public String getBuildNumber() {
	  return buildNumber;
  }
  public void setBuildNumber(String buildNumber) {
	  this.buildNumber = buildNumber;
  }
  
  public void loadProperties(Data properties) {
	  for (Data prop : properties.getDataList()) {
		  List<Data> pair = prop.getClusterAsList();
		  String propName = pair.get(0).getString();
		  Long propValue = pair.get(1).getWord();
		  buildProperties.put(propName, propValue);
		  //System.out.println("put: " + propName + " -- " + propValue);
	  }
  }
  public Map<String, Long> getBuildProperties() {
	  return this.buildProperties;
  }

  public void setFiber(DacFiberId fiber, BiasBoard board, DcRackFiberId channel) {
    fibers.put(fiber, board);
    fiberChannels.put(fiber, channel);
  }
}
