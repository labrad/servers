package org.labrad.qubits.channeldata;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.PacketResultHandler;

import com.google.common.base.Preconditions;

public class IqDataTime extends IqDataBase {

	private ComplexArray data;
	private int[] I, Q;
	
	public IqDataTime(ComplexArray data, boolean isDeconvolved) {
		this.data = data;
		if (isDeconvolved) {
			I = new int[data.re.length];
			Q = new int[data.im.length];
			for (int i = 0; i < data.length; i++) {
				I[i] = (int)(data.re[i] * 0x1fff) & 0x3fff;
				Q[i] = (int)(data.im[i] * 0x1fff) & 0x3fff;
			}
		}
		setDeconvolved(isDeconvolved);
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
		final int idx = req.addRecord("Correct", data.toData());
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
