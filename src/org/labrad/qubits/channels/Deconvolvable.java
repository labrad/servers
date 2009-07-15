package org.labrad.qubits.channels;

import org.labrad.data.Request;
import org.labrad.qubits.util.PacketResultHandler;

public interface Deconvolvable {
	/**
	 * Whether the data for this block has been deconvolved
	 * @return
	 */
	public boolean isDeconvolved();
	
	/**
	 * Add instructions to deconvolve this block to a request headed for the deconvolution server.
	 * @param req
	 * @return
	 */
	public PacketResultHandler requestDeconvolution(Request req);
}
