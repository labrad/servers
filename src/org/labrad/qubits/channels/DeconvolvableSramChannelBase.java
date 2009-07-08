package org.labrad.qubits.channels;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.data.Request;

import com.google.common.collect.Lists;

public abstract class DeconvolvableSramChannelBase<T> extends SramChannelBase<T> implements
		DeconvolvableSramChannel {

	protected abstract Deconvolvable getBlockData(String blockName);
	
	public PacketResultHandler requestDeconvolution(Request req) {
		final List<PacketResultHandler> handlers = Lists.newArrayList();
		for (String blockName : expt.getBlockNames()) {
			Deconvolvable block = getBlockData(blockName);
			if (!block.isDeconvolved()) {
				handlers.add(block.requestDeconvolution(req));
			}
		}
		return new PacketResultHandler() {
			@Override
			public void handleResult(List<Data> data) {
				for (PacketResultHandler handler : handlers) {
					handler.handleResult(data);
				}
			}
		};
	}
}
