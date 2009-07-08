package org.labrad.qubits.channels;

import org.labrad.data.Request;

public interface DeconvolvableSramChannel extends SramChannel {
	public PacketResultHandler requestDeconvolution(Request req);
}
