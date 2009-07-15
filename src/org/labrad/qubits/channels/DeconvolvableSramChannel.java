package org.labrad.qubits.channels;

import org.labrad.data.Request;
import org.labrad.qubits.util.PacketResultHandler;

public interface DeconvolvableSramChannel extends SramChannel {
	public PacketResultHandler requestDeconvolution(Request req);
}
