package org.labrad.qubits.util;

import java.util.List;

import org.labrad.data.Data;

public interface PacketResultHandler {
	public void handleResult(List<Data> data);
}
