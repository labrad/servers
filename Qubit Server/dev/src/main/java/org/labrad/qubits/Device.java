package org.labrad.qubits;

import java.util.List;
import java.util.Map;

import org.labrad.qubits.channels.Channel;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;

/**
 * Model of a device, essentially a collection of named channels of various types.
 * Each channel connects various physical devices (FastBias, Preamp, GHzDac) to some
 * controllable parameter on the device (flux bias, microwave, etc.).
 * 
 * @author maffoo
 */
public class Device {
  private String name;
  private List<Channel> channels = Lists.newArrayList();
  private Map<String, Channel> channelsByName = Maps.newHashMap();

  public Device(String name) {
    this.name = name;
  }

  public String getName() {
    return name;
  }

  /**
   * Add a channel to this device.
   * @param ch
   */
  public void addChannel(Channel ch) {
    channels.add(ch);
    channelsByName.put(ch.getName(), ch);
  }

  /**
   * Get all defined channels.
   * @return
   */
  public List<Channel> getChannels() {
    return Lists.newArrayList(channels);
  }

  /**
   * Get all channels of a particular type.
   * @param <T>
   * @param cls
   * @return
   */
  @SuppressWarnings("unchecked")
  public <T extends Channel> List<T> getChannels(Class<T> cls) {
    List<T> matches = Lists.newArrayList();
    for (Channel chan : channels) {
      if (cls.isInstance(chan)) {
        matches.add((T)chan);
      }
    }
    return matches;
  }

  /**
   * Get a channel by name (of any type).
   * @param name
   * @return
   */
  public Channel getChannel(String name) {
    Preconditions.checkArgument(channelsByName.containsKey(name),
        "Device '%s' has no channel named '%s'", getName(), name);
    return channelsByName.get(name);
  }

  /**
   * Get a channel by name and type.
   * @param <T>
   * @param name
   * @param cls
   * @return
   */
  @SuppressWarnings("unchecked")
  public <T extends Channel> T getChannel(String name, Class<T> cls) {
    Channel ch = getChannel(name);
    Preconditions.checkState(cls.isInstance(ch),
        "Channel '%s' is not of type '%s'", name, cls.getName());
    return (T)ch;
  }

  /**
   * Get a channel by type only.  This fails if there is more than one channel with the desired type.
   * @param <T>
   * @param cls
   * @return
   */
  public <T extends Channel> T getChannel(Class<T> cls) {
    List<T> channels = getChannels(cls);
    Preconditions.checkState(channels.size() == 1,
        "Device '%s' has more than one channel of type '%s'", getName(), cls.getName());
    return channels.get(0);
  }
}
