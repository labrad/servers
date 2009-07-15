package org.labrad.qubits.channeldata;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.PacketResultHandler;

import com.google.common.base.Preconditions;

public class IqDataFourier extends IqDataBase {

	private ComplexArray data;
	private double t0;
	private int[] I, Q;
	
	public IqDataFourier(ComplexArray data, double t0) {
		this.data = data;
		this.t0 = t0;
	}

	public void checkLength(int expected) {
		LengthChecker.checkLengths(data.length, expected);
	}
	
	@Override
	public PacketResultHandler requestDeconvolution(Request req) {
		IqChannel channel = getChannel();
		String board = channel.getDacBoard().getName();
		double freq = channel.getMicrowaveConfig().getFrequency();
		req.add("Board", Data.valueOf(board));
		req.add("Frequency", Data.valueOf(freq));
		req.add("Loop", Data.valueOf(false));
		req.add("Time Offset", Data.valueOf(t0));
		final int idx = req.addRecord("Correct FT", data.toData());
		return new PacketResultHandler() {
			public void handleResult(List<Data> ans) {
				Data data = ans.get(idx);
				I = data.get(0).getIntArray();
				Q = data.get(1).getIntArray();
				setDeconvolved(true);
			}
		};
	}
	
	@Override
	public int[] getDeconvolvedI() {
		Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
		return I;
	}
	
	@Override
	public int[] getDeconvolvedQ() {
		Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
		return Q;
	}
}
