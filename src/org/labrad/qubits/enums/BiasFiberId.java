package org.labrad.qubits.enums;

import java.util.Map;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public enum BiasFiberId {
	A("a"),
	B("b"),
	C("c"),
	D("d");
	
	private final String name;
	private static final Map<String, BiasFiberId> map = Maps.newHashMap();
	
	BiasFiberId(String name) {
		this.name = name;
	}
	
	public String toString() {
		return name;
	}
	
	static {
		for (BiasFiberId id : values()) {
			map.put(id.name, id);
		}
	}
	
	public static BiasFiberId fromString(String name) {
		String key = name.toLowerCase();
		Preconditions.checkArgument(map.containsKey(key),
				"Invalid bias channel id '%s'", name);
		return map.get(key);
	}
}
