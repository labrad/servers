package org.labrad.qubits.resources;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.labrad.data.Data;
import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;
import org.labrad.qubits.enums.DeviceType;

import com.google.common.base.Preconditions;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;


/**
 * "Resources represent the available hardware; these are configured in the registry."
 * 
 * @author maffoo
 */
public class Resources {
  // instance is an immutable map from string names to resources
  private final Map<String, Resource> resources;

  // private constructor for building a set of resources
  private Resources(Map<String, Resource> resources) {
    this.resources = ImmutableMap.copyOf(resources);
  }

  /**
   * Get a resource by name, ensuring that it is of a particular type
   * @param <T>
   * @param name
   * @param cls
   * @return
   */
  @SuppressWarnings("unchecked")
  public <T extends Resource> T get(String name, Class<? extends T> cls) {
    Preconditions.checkArgument(resources.containsKey(name),
        "Resource '%s' not found", name);
    Resource r = resources.get(name);
    Preconditions.checkArgument(cls.isInstance(r),
        "Resource '%s' not of type %s", name, cls.getName());	
    return (T) r;
  }
  
  /**
   * Get all resources of a given type.
   * @param <T>
   * @param cls
   * @return
   */
  @SuppressWarnings("unchecked")
  public <T extends Resource> List<T> getAll(Class<? extends T> cls) {
	  List<T> list = Lists.newArrayList();
	  for (String key : resources.keySet()) {
		  Resource r = resources.get(key);
		  if (cls.isInstance(r)) {
			  list.add((T)r);
		  }
	  }
	  return list;
  }


  /**
   * Create a resource of the given type.
   * @param type
   * @param name
   * @return
   */
  public static Resource create(DeviceType type, String name, List<Data> properties) {
    switch (type) {
      case UWAVEBOARD: return MicrowaveBoard.create(name);
      case ANALOGBOARD: return AnalogBoard.create(name);
      case FASTBIAS: return FastBias.create(name, properties);
      case PREAMP: return PreampBoard.create(name);
      case UWAVESRC: return MicrowaveSource.create(name);
      case ADCBOARD: return AdcBoard.create(name);
      default: throw new RuntimeException("Invalid resource type: " + type);
    }
  }
  /**
   * Create new wiring configuration and update the current config.
   * @param resources
   * @param fibers
   * @param microwaves
   */
  public static void updateWiring(List<Data> resources, List<Data> fibers, List<Data> microwaves) {
  	/*
  	 * resources - [(String type, String id),...]
  	 * fibers - [((dacName, fiber),(cardName, channel)),...]
  	 */
    // build resources for all objects
    Map<String, Resource> map = Maps.newHashMap();
    for (Data elem : resources) {
  		String type = elem.get(0).getString();
  		String name = elem.get(1).getString();
      List<Data> properties = (elem.getClusterSize() == 3) ? elem.get(2).getClusterAsList()
      		                                                 : new ArrayList<Data>();
      DeviceType dt = DeviceType.fromString(type);
      map.put(name, create(dt, name, properties));
    }
    Resources r = new Resources(map);

    // wire together DAC boards and bias boards
    for (Data elem : fibers) {
      String dacName = elem.get(0, 0).getString();
      String fiber = elem.get(0, 1).getString();
      String cardName = elem.get(1, 0).getString();
      String channel = elem.get(1, 1).getString();

      DacBoard dac = r.get(dacName, DacBoard.class);
      BiasBoard bias = r.get(cardName, BiasBoard.class);
      DacFiberId df = DacFiberId.fromString(fiber);
      DcRackFiberId bf = DcRackFiberId.fromString(channel);
      dac.setFiber(df, bias, bf);
      bias.setDacBoard(bf, dac, df);
    }

    // wire together microwave DAC boards and microwave sources
    for (Data elem : microwaves) {
      String dacName = elem.get(0).getString();
      String devName = elem.get(1).getString();

      MicrowaveBoard dac = r.get(dacName, MicrowaveBoard.class);
      MicrowaveSource uwaveSrc = r.get(devName, MicrowaveSource.class);
      dac.setMicrowaveSource(uwaveSrc);
      uwaveSrc.addMicrowaveBoard(dac);
    }

    // Set this new resource map as the current one
    setCurrent(r);
  }

  // we keep a single instance containing the current resource map.
  // updates to this instance are protected by a thread lock
  private static Resources current = null;
  private static final Object updateLock = new Object();

  /**
   * Set a new resource collection as the current collection
   * @param resources
   */
  private static void setCurrent(Resources resources) {
    synchronized (updateLock) {
      current = resources;
    }
  }

  /**
   * Get the current resource collection
   * @return
   */
  public static Resources getCurrent() {
    synchronized (updateLock) {
      return current;
    }
  }
}
