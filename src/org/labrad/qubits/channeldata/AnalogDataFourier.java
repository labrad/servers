package org.labrad.qubits.channeldata;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.PacketResultHandler;

import com.google.common.base.Preconditions;

public class AnalogDataFourier extends AnalogDataBase {

	private ComplexArray data;
	private double t0;
	private int[] deconvolvedData;
	
	public AnalogDataFourier(ComplexArray data, double t0) {
		this.data = data;
		this.t0 = t0;
	}
	
	public void checkLength(int expected) {
		int expectedFourier = expected % 2 == 0 ? (expected/2) + 1 : (expected+1) / 2;
		LengthChecker.checkLengths(data.length, expectedFourier);
	}
	
	/**
	 * Add commands to deconvolve this block to a request headed for the
	 * deconvolution server.  Returns an object that will handle the
	 * deconvolved result when it is available.
	 */
	@Override
	public PacketResultHandler requestDeconvolution(Request req) {
		AnalogChannel ch = getChannel();
		String board = ch.getDacBoard().getName();
		double[] rates = ch.getSettlingRates();
		double[] times = ch.getSettlingTimes();
		req.add("Board", Data.valueOf(board));
		req.add("DAC", Data.valueOf(ch.getDacId().toString()));
		req.add("Loop", Data.valueOf(false));
		req.add("Set Settling", Data.clusterOf(Data.valueOf(rates), Data.valueOf(times)));
		req.add("Time Offset", Data.valueOf(t0));
		final int idx = req.addRecord("Correct FT", data.toData());
		return new PacketResultHandler() {
			public void handleResult(List<Data> data) {
				deconvolvedData = data.get(idx).getIntArray();
				setDeconvolved(true);
			}
		};
	}
	
	@Override
	public int[] getDeconvolved() {
		Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
		return deconvolvedData;
	}
}
