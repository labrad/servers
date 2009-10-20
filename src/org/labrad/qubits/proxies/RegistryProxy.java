package org.labrad.qubits.proxies;

import java.util.List;
import java.util.Map;

import org.labrad.Connection;
import org.labrad.Failure;
import org.labrad.data.Context;
import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.data.Setters;

import com.google.common.collect.Lists;
import com.google.common.collect.Maps;

public class RegistryProxy {
  public final static String SERVER_NAME = "Registry";
  public final static String CHANNEL_TYPE = "s *s";
  public final static String[] WIRING_PATH = {"", "Servers", "Qubit Server", "Wiring"};
  public final static String WIRING_KEY = "wiring";
  public final static String WIRING_TYPE = "*(ss), *((ss)(ss)), *(ss)";

  /**
   * Load a list of devices from the registry
   * @param names list of device names to load
   * @param aliases list of aliases to use for the devices once loaded
   * @param cxn the LabRAD connection object
   * @param c the context in which to do the loading
   * @return
   */
  public static Data loadDevices(List<String> path, List<String> names, List<String> aliases, Connection cxn, Context c) {
    List<Data> devices = Lists.newArrayList();
    for (int i = 0; i < names.size(); i++) {
      String name = names.get(i);
      String alias = aliases.get(i);
      devices.add(loadDevice(path, name, alias, cxn, c));
    }
    return Data.listOf(devices);
  }

  /**
   * Load a single device from the registry
   * @param name
   * @param alias
   * @param cxn
   * @param c
   * @return
   */
  private static Data loadDevice(List<String> path, String name, String alias, Connection cxn, Context c) {
    Context ctx = cxn.newContext();
    Request req;

    // get a directory listing to find all keys for this device
    req = startRequest(ctx, path, name);
    int idx = req.addRecord("dir");
    List<String> keys = null;
    try {
      keys = cxn.sendAndWait(req).get(idx).get(1).getStringList();
    } catch (Exception ex) {
      Failure.fail("Failed to load device '%s' from the registry.", name);
    }

    // get the value of each key, making sure it is of the expected type for a channel
    req = startRequest(ctx, path, name);
    Map<String, Integer> indices = Maps.newHashMap();
    for (String channel : keys) {
      int i = req.addRecord("get", Data.valueOf(channel), Data.valueOf(CHANNEL_TYPE));
      indices.put(channel, i);
    }
    List<Data> answers = null;
    try {
      answers = cxn.sendAndWait(req);
    } catch (Exception ex) {
      Failure.fail("Failed to load device '%s' from the registry.", name);
    }

    // build a list of the channels
    List<Data> channels = Lists.newArrayList();
    for (String channel : keys) {
      Data value = answers.get(indices.get(channel));
      channels.add(Data.clusterOf(Data.valueOf(channel), value));
    }

    // return the device cluster
    return Data.clusterOf(Data.valueOf(alias), Data.listOf(channels));
  }

  private static Request startRequest(Context ctx, List<String> path, String name) {
    Request req = Request.to(SERVER_NAME, ctx);
    req.add("Duplicate Context", Data.valueOf(ctx.getHigh()), Data.valueOf(ctx.getLow()));
    req.add("cd", Data.listOf(path, Setters.stringSetter));
    req.add("cd", Data.valueOf(name));
    return req;
  }
}
