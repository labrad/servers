package org.labrad.qubits;

import java.util.List;
import java.util.Map;

import org.labrad.qubits.channels.Channel;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;

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
	
	public void addChannel(Channel ch) {
		channels.add(ch);
		channelsByName.put(ch.getName(), ch);
	}
	
	public List<Channel> getChannels() {
		return Lists.newArrayList(channels);
	}
	
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
	
	public Channel getChannel(String name) {
		Preconditions.checkArgument(channelsByName.containsKey(name),
			"Device '%s' has no channel named '%s'", getName(), name);
		return channelsByName.get(name);
	}
	
	@SuppressWarnings("unchecked")
	public <T extends Channel> T getChannel(String name, Class<T> cls) {
		Preconditions.checkArgument(channelsByName.containsKey(name),
			"Device '%s' has no channel named '%s'", getName(), name);
		Channel ch = channelsByName.get(name);
		Preconditions.checkState(cls.isInstance(ch),
			"Channel '%s' is not of type '%s'", name, cls.getName());
		return (T)ch;
	}
	
	public <T extends Channel> T getChannel(Class<T> cls) {
		List<T> channels = getChannels(cls);
		Preconditions.checkState(channels.size() == 1,
			"Device '%s' has more than one channel of type '%s'", getName(), cls.getName());
		return channels.get(0);
	}
}
